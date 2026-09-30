from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas


class ProductNotFoundError(Exception):
    pass


class InventoryNotFoundError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class DuplicateSKUError(Exception):
    pass


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
    except IntegrityError:
        db.rollback()
        raise DuplicateSKUError("El SKU ya existe")


def get_products(db: Session):
    return db.query(models.Product).all()


def get_product_by_id(db: Session, product_id: int):
    return (
        db.query(models.Product)
        .filter(models.Product.id == product_id)
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
    except IntegrityError:
        db.rollback()
        raise DuplicateSKUError("El SKU ya existe")


def delete_product(db: Session, product_id: int):
    db_product = get_product_by_id(db, product_id)

    if db_product is None:
        raise ProductNotFoundError("Producto no encontrado")

    db.delete(db_product)
    db.commit()

    return True


# -------------------------
# INVENTARIO
# -------------------------

def get_inventory(db: Session, product_id: int, warehouse_id: int = 1):
    return (
        db.query(models.Inventory)
        .filter(
            models.Inventory.product_id == product_id,
            models.Inventory.warehouse_id == warehouse_id,
        )
        .first()
    )


def get_inventory_movements(
    db: Session,
    product_id: int,
    warehouse_id: int = 1,
):
    return (
        db.query(models.InventoryMovement)
        .filter(
            models.InventoryMovement.product_id == product_id,
            models.InventoryMovement.warehouse_id == warehouse_id,
        )
        .order_by(models.InventoryMovement.created_at.desc())
        .all()
    )


def process_inventory_movement(
    db: Session,
    movement: schemas.MovementCreate,
):
    with db.begin():

        # Verificar que el producto exista
        product = (
            db.query(models.Product)
            .filter(models.Product.id == movement.product_id)
            .first()
        )

        if product is None:
            raise ProductNotFoundError("Producto no encontrado")

        # Bloquear el inventario mientras se procesa el movimiento
        inventory = (
            db.query(models.Inventory)
            .filter(
                models.Inventory.product_id == movement.product_id,
                models.Inventory.warehouse_id == movement.warehouse_id,
            )
            .with_for_update()
            .first()
        )

        # Si todavía no existe inventario para el producto
        if inventory is None:

            if movement.type == models.MovementType.SHIPMENT:
                raise InsufficientStockError(
                    "Stock insuficiente para realizar la salida"
                )

            inventory = models.Inventory(
                product_id=movement.product_id,
                warehouse_id=movement.warehouse_id,
                quantity=0,
                reserved_quantity=0,
            )

            db.add(inventory)
            db.flush()

        # Entrada de inventario
        if movement.type == models.MovementType.RECEIPT:
            inventory.quantity += movement.quantity

        # Salida de inventario
        elif movement.type == models.MovementType.SHIPMENT:

            if inventory.quantity < movement.quantity:
                raise InsufficientStockError(
                    "Stock insuficiente para realizar la salida"
                )

            inventory.quantity -= movement.quantity

        # Registrar el movimiento
        db_movement = models.InventoryMovement(
            product_id=movement.product_id,
            warehouse_id=movement.warehouse_id,
            type=movement.type,
            quantity=movement.quantity,
            reference=movement.reference,
        )

        db.add(db_movement)
        db.flush()

    return db_movement
