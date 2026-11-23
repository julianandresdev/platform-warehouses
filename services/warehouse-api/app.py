import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

import cache
import config
import schemas
import services
from common.correlation import CorrelationIdMiddleware
from common.logging import configure_logging
from database import get_db

configure_logging("warehouse-api", config.WAREHOUSE_ID, config.LOG_LEVEL)
logger = logging.getLogger("warehouse-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate_settings()
    yield


app = FastAPI(
    title="Warehouse Cloud Platform",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        },
    )
    return response


# Se agrega al final para que sea la capa más externa: el correlation ID ya está
# fijado cuando corre el log de arriba.
app.add_middleware(CorrelationIdMiddleware)


def require_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode(), config.API_KEY.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o ausente",
        )


# Todo lo que cuelga de este router exige el header X-API-Key.
# Solo /health y /health/ready quedan abiertos (los usan Docker y el balanceador).
protected = APIRouter(dependencies=[Depends(require_api_key)])


# -------------------------
# HEALTH
# -------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL no responde",
        )
    return {"status": "ready", "warehouse_id": config.WAREHOUSE_ID}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# -------------------------
# PRODUCTOS
# -------------------------

@protected.post(
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
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )


@protected.get(
    "/products",
    response_model=list[schemas.ProductResponse],
)
def get_products(db: Session = Depends(get_db)):
    return services.get_products(db)


@protected.get(
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


@protected.put(
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
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )


@protected.delete(
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

    except services.ProductInUseError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )


# -------------------------
# INVENTARIO (de la bodega definida por WAREHOUSE_ID)
# -------------------------

@protected.post(
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

    except (
        services.InsufficientStockError,
        services.InvalidAdjustmentError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )


@protected.get(
    "/inventory/{sku}",
    response_model=schemas.InventoryResponse,
)
def get_inventory(
    sku: str,
    response: Response,
    db: Session = Depends(get_db),
):
    cached, cache_status = cache.get_inventory(sku)
    response.headers["X-Cache"] = cache_status
    if cached is not None:
        return cached

    inventory = services.get_inventory(db, sku)

    if inventory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventario no encontrado",
            headers={"X-Cache": cache_status},
        )

    if cache_status == cache.MISS:
        cache.set_inventory(
            sku,
            schemas.InventoryResponse.model_validate(inventory).model_dump(mode="json"),
        )

    return inventory


@protected.get(
    "/inventory/{sku}/movements",
    response_model=list[schemas.MovementResponse],
)
def get_inventory_movements(
    sku: str,
    db: Session = Depends(get_db),
):
    return services.get_inventory_movements(db, sku)


app.include_router(protected)
