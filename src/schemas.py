from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models import MovementType


class ProductCreate(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str


class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    sku: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MovementCreate(BaseModel):
    product_id: int
    warehouse_id: int = 1
    type: MovementType
    quantity: int = Field(gt=0)
    reference: Optional[str] = None


class InventoryResponse(BaseModel):
    id: int
    product_id: int
    warehouse_id: int
    quantity: int
    reserved_quantity: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MovementResponse(BaseModel):
    id: int
    product_id: int
    warehouse_id: int
    type: MovementType
    quantity: int
    reference: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
