from enum import Enum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, func
from sqlalchemy.orm import relationship
from src.database import Base


class MovementType(str, Enum):
    RECEIPT = "RECEIPT"
    SHIPMENT = "SHIPMENT"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    unit = Column(String(20), default="unit", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Inventory(Base):
    __tablename__ = "inventories"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(String(50), nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    reserved_quantity = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(String(50), nullable=False)
    type = Column(SQLEnum(MovementType), nullable=False)
    quantity = Column(Integer, nullable=False)
    reference = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)