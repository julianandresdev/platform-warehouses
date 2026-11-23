from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import cache
import config
import models
import schemas
from common.events import new_event
from common.outbox import add_event

# Códigos SQLSTATE de PostgreSQL
UNIQUE_VIOLATION = "23505"
# Con ON DELETE RESTRICT PostgreSQL responde 23001 (restrict_violation);
# con NO ACTION o al insertar una referencia inexistente responde 23503.
RESTRICT_VIOLATION = "23001"
FOREIGN_KEY_VIOLATION = "23503"


class ProductNotFoundError(Exception):
    pass


class InventoryNotFoundError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class DuplicateSKUError(Exception):
    pass


class ProductInUseError(Exception):
    """El producto tiene inventario o movimientos asociados."""


class InvalidAdjustmentError(Exception):
    """El conteo físico no se puede aplicar (bajo lo reservado o sin diferencia)."""


def _sqlstate(error: IntegrityError):
    return getattr(error.orig, "pgcode", None)


# -------------------------
# PRODUCTOS
# -------------------------

def create_product(db: Session, product: schemas.ProductCreate):
    db_product = models.Product(**product.model_dump())

    try:
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        return db_product
    except IntegrityError as error:
        db.rollback()
        if _sqlstate(error) == UNIQUE_VIOLATION:
            raise DuplicateSKUError("El SKU ya existe")
        raise


def get_products(db: Session):
    return db.query(models.Product).order_by(models.Product.id).all()


def get_product_by_id(db: Session, product_id: int):
    return (
        db.query(models.Product)
        .filter(models.Product.id == product_id)
        .first()
    )


def get_product_by_sku(db: Session, sku: str):
    return (
        db.query(models.Product)
        .filter(models.Product.sku == sku)
        .first()
    )


def update_product(
    db: Session,
    product_id: int,
    product: schemas.ProductUpdate,
):
    db_product = get_product_by_id(db, product_id)

    if db_product is None:
        raise ProductNotFoundError("Producto no encontrado")

    data = product.model_dump(exclude_unset=True)

    for field, value in data.items():
        setattr(db_product, field, value)

    try:
        db.commit()
        db.refresh(db_product)
        return db_product
    except IntegrityError as error:
        db.rollback()
        if _sqlstate(error) == UNIQUE_VIOLATION:
            raise DuplicateSKUError("El SKU ya existe")
        raise


def delete_product(db: Session, product_id: int):
    db_product = get_product_by_id(db, product_id)

    if db_product is None:
        raise ProductNotFoundError("Producto no encontrado")

    try:
        db.delete(db_product)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # Las llaves foráneas son RESTRICT: con movimientos o inventario no se borra.
        if _sqlstate(error) in (RESTRICT_VIOLATION, FOREIGN_KEY_VIOLATION):
            raise ProductInUseError(
                "No se puede eliminar un producto con inventario o movimientos"
            )
        raise

    return True


# -------------------------
# INVENTARIO
# -------------------------

def get_inventory(db: Session, sku: str):
    return (
        db.query(models.Inventory)
        .join(models.Product, models.Inventory.product_id == models.Product.id)
        .filter(
            models.Product.sku == sku,
            models.Inventory.warehouse_id == config.WAREHOUSE_ID,
        )
        .first()
    )


def get_inventory_movements(db: Session, sku: str):
    return (
        db.query(models.InventoryMovement)
        .join(
            models.Product,
            models.InventoryMovement.product_id == models.Product.id,
        )
        .filter(
            models.Product.sku == sku,
            models.InventoryMovement.warehouse_id == config.WAREHOUSE_ID,
        )
        .order_by(
            models.InventoryMovement.created_at.desc(),
            models.InventoryMovement.id.desc(),
        )
        .all()
    )


def process_inventory_movement(
    db: Session,
    movement: schemas.MovementCreate,
):
    warehouse_id = config.WAREHOUSE_ID

    # Si algo falla dentro del bloque se hace rollback completo: no queda ni el
    # movimiento ni la fila de inventario creada para el bloqueo (ADR-0004).
    with db.begin():

        product = get_product_by_sku(db, movement.sku)

        if product is None:
            raise ProductNotFoundError("Producto no encontrado")

        # 1. Garantizar que la fila de inventario exista. Sin esto, el primer
        #    RECEIPT concurrente no tiene fila que bloquear y se crearían dos.
        #    Si otra transacción la está creando, ON CONFLICT espera a que termine.
        db.execute(
            pg_insert(models.Inventory)
            .values(
                product_id=product.id,
                warehouse_id=warehouse_id,
                quantity=0,
                reserved_quantity=0,
                version=0,
            )
            .on_conflict_do_nothing(
                index_elements=["product_id", "warehouse_id"]
            )
        )

        # 2. Bloquear la fila mientras se procesa el movimiento.
        inventory = (
            db.query(models.Inventory)
            .filter(
                models.Inventory.product_id == product.id,
                models.Inventory.warehouse_id == warehouse_id,
            )
            .with_for_update(of=models.Inventory)
            .populate_existing()
            .one()
        )

        recorded_quantity = movement.quantity

        if movement.type == models.MovementType.RECEIPT:
            inventory.quantity += movement.quantity

        elif movement.type == models.MovementType.SHIPMENT:
            # Se valida contra lo disponible: lo reservado no se puede despachar.
            available = inventory.quantity - inventory.reserved_quantity
            if movement.quantity > available:
                raise InsufficientStockError(
                    "Stock insuficiente para realizar la salida"
                )
            inventory.quantity -= movement.quantity

        elif movement.type == models.MovementType.ADJUSTMENT:
            # Conteo físico: movement.quantity es lo contado; se registra la
            # diferencia (puede ser negativa).
            if movement.quantity < inventory.reserved_quantity:
                raise InvalidAdjustmentError(
                    "El conteo no puede ser menor que la cantidad reservada"
                )
            recorded_quantity = movement.quantity - inventory.quantity
            if recorded_quantity == 0:
                raise InvalidAdjustmentError(
                    "El conteo coincide con el inventario: no hay diferencia que registrar"
                )
            inventory.quantity = movement.quantity

        inventory.version += 1

        db_movement = models.InventoryMovement(
            product_id=product.id,
            warehouse_id=warehouse_id,
            type=movement.type,
            quantity=recorded_quantity,
            reference=movement.reference,
        )

        db.add(db_movement)
        db.flush()

        event = new_event(
            event_type="INVENTORY_UPDATED",
            payload={
                "warehouse_id": warehouse_id,
                "sku": product.sku,
                "quantity": inventory.quantity,
                "reserved_quantity": inventory.reserved_quantity,
                "version": inventory.version,
                "movement_type": movement.type.value,
            },
            source=f"warehouse-{warehouse_id}",
        )
        add_event(
            db,
            event,
            exchange="warehouse.events",
            routing_key=f"warehouse.{warehouse_id}.inventory.updated",
        )

    # Ya hay COMMIT. Invalidar antes dejaría que una lectura concurrente volviera
    # a cachear el valor viejo (ADR-0008).
    cache.invalidate_inventory(movement.sku)

    return db_movement
