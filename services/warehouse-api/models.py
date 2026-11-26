"""Modelos SQLAlchemy.

Reflejan infrastructure/sql/warehouse/schema.sql, que es la fuente de verdad del
esquema. Si cambia una tabla, se cambia primero el SQL (schema.sql o una
migración) y después este archivo.
"""
import enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class MovementType(str, enum.Enum):
    RECEIPT = "RECEIPT"
    SHIPMENT = "SHIPMENT"
    ADJUSTMENT = "ADJUSTMENT"
    # Movimientos de la Saga de transferencias (migración 002). Solo los genera
    # el worker de comandos; la API no los acepta en POST /inventory/movements.
    RESERVATION = "RESERVATION"
    RESERVATION_RELEASE = "RESERVATION_RELEASE"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_RETURN = "TRANSFER_RETURN"


# Tipos que un cliente puede registrar a mano por la API.
MANUAL_MOVEMENT_TYPES = frozenset(
    {MovementType.RECEIPT, MovementType.SHIPMENT, MovementType.ADJUSTMENT}
)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    sku = Column(String(100), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "warehouse_id", name="uq_inventory_product_warehouse"
        ),
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity_non_negative"),
        CheckConstraint(
            "reserved_quantity >= 0 AND reserved_quantity <= quantity",
            name="ck_inventory_reserved_valid",
        ),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    warehouse_id = Column(String(20), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    reserved_quantity = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    product = relationship("Product", lazy="joined")

    @property
    def sku(self) -> str:
        return self.product.sku

    @property
    def available_quantity(self) -> int:
        return self.quantity - self.reserved_quantity


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("quantity <> 0", name="ck_movements_quantity_not_zero"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    warehouse_id = Column(String(20), nullable=False)
    type = Column(
        Enum(MovementType, name="movement_type", create_type=False),
        nullable=False,
    )
    quantity = Column(Integer, nullable=False)
    reference = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    product = relationship("Product", lazy="joined")

    @property
    def sku(self) -> str:
        return self.product.sku


class ReportJob(Base):
    __tablename__ = "report_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PROCESSING', 'DONE', 'FAILED')",
            name="ck_report_jobs_status",
        ),
    )

    job_id = Column(Uuid(as_uuid=True), primary_key=True)
    status = Column(String(20), nullable=False)
    params = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
