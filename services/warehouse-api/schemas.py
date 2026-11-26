from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models import MANUAL_MOVEMENT_TYPES, MovementType


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    unit: str = Field(min_length=1, max_length=50)


class ProductUpdate(BaseModel):
    sku: Optional[str] = Field(default=None, min_length=1, max_length=100)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=50)


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
    """Movimiento de inventario de ESTA bodega (la define WAREHOUSE_ID).

    - RECEIPT / SHIPMENT: `quantity` son las unidades que entran o salen (> 0).
    - ADJUSTMENT: conteo físico. `quantity` es la cantidad contada (>= 0); el
      movimiento registrado guarda la diferencia contra el inventario.
    """

    sku: str = Field(min_length=1, max_length=100)
    type: MovementType
    quantity: int = Field(ge=0)
    reference: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def type_must_be_manual(self):
        # Los movimientos de transferencia los registra solo el worker de la Saga.
        if self.type not in MANUAL_MOVEMENT_TYPES:
            raise ValueError("type debe ser RECEIPT, SHIPMENT o ADJUSTMENT")
        return self

    @model_validator(mode="after")
    def quantity_must_be_positive_unless_adjustment(self):
        if self.type != MovementType.ADJUSTMENT and self.quantity <= 0:
            raise ValueError("quantity debe ser mayor que 0")
        return self


class InventoryResponse(BaseModel):
    id: int
    sku: str
    product_id: int
    warehouse_id: str
    quantity: int
    reserved_quantity: int
    available_quantity: int
    version: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MovementResponse(BaseModel):
    id: int
    sku: str
    product_id: int
    warehouse_id: str
    type: MovementType
    quantity: int
    reference: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
