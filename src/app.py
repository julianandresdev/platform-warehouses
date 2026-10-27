from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy.orm import Session

import schemas
import services
from database import get_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Warehouse Cloud Platform",
    lifespan=lifespan,
)


# -------------------------
# HEALTH
# -------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# -------------------------
# PRODUCTOS
# -------------------------

@app.post(
    "/products",
    response_model=schemas.ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(get_db),
):
    try:
        return services.create_product(db, product)
    except services.DuplicateSKUError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@app.get(
    "/products",
    response_model=list[schemas.ProductResponse],
)
def get_products(db: Session = Depends(get_db)):
    return services.get_products(db)


@app.get(
    "/products/{product_id}",
    response_model=schemas.ProductResponse,
)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = services.get_product_by_id(db, product_id)

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )

    return product


@app.put(
    "/products/{product_id}",
    response_model=schemas.ProductResponse,
)
def update_product(
    product_id: int,
    product: schemas.ProductUpdate,
    db: Session = Depends(get_db),
):
    try:
        return services.update_product(db, product_id, product)

    except services.ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )

    except services.DuplicateSKUError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@app.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    try:
        services.delete_product(db, product_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except services.ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )


# -------------------------
# INVENTARIO
# -------------------------

@app.get(
    "/inventory/{product_id}",
    response_model=schemas.InventoryResponse,
)
def get_inventory(
    product_id: int,
    db: Session = Depends(get_db),
):
    inventory = services.get_inventory(db, product_id)

    if inventory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventario no encontrado",
        )

    return inventory


@app.post(
    "/inventory/movements",
    response_model=schemas.MovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_movement(
    movement: schemas.MovementCreate,
    db: Session = Depends(get_db),
):
    try:
        return services.process_inventory_movement(db, movement)

    except services.ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        )

    except services.InsufficientStockError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@app.get(
    "/inventory/{product_id}/movements",
    response_model=list[schemas.MovementResponse],
)
def get_inventory_movements(
    product_id: int,
    db: Session = Depends(get_db),
):
    return services.get_inventory_movements(db, product_id)
