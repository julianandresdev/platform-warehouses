from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from src.models import MovementType


# --- DTOs de Productos ---

class ProductCreate(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str = "unit"


class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None


class ProductResponse(ProductCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- DTOs de Inventarios y Movimientos ---

class MovementCreate(BaseModel):
    product_id: int
    warehouse_id: str
    type: MovementType
    quantity: int = Field(..., gt=0, description="Cantidad mayor a 0")
    reference: Optional[str] = None


class InventoryResponse(BaseModel):
    id: int
    product_id: int
    warehouse_id: str
    quantity: int
    reserved_quantity: int
    updated_at: datetime

    class Config:
        from_attributes = True