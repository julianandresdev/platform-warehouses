import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter, Depends, FastAPI,
    Header, HTTPException, Query, status
)
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from common.correlation import CorrelationIdMiddleware
from common.logging import configure_logging

from app import config
from app.domain.database import get_db


# --------------------------------------------------
# CONFIGURACION Y LOGS
# --------------------------------------------------

configure_logging(
    config.SERVICE_NAME,
    None,
    config.LOG_LEVEL
)

logger = logging.getLogger(config.SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate_settings()
    yield


app = FastAPI(
    title="Warehouse Central API",
    version="1.0.0",
    lifespan=lifespan
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
            "duration_ms": round(
                (time.perf_counter() - start) * 1000, 2
            )
        }
    )

    return response


app.add_middleware(CorrelationIdMiddleware)


# --------------------------------------------------
# AUTENTICACION
# --------------------------------------------------

def require_api_key(
    x_api_key: str | None = Header(default=None)
):
    if (
        x_api_key is None
        or not secrets.compare_digest(
            x_api_key.encode(),
            config.API_KEY.encode()
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key invalida o ausente"
        )


protected = APIRouter(
    dependencies=[Depends(require_api_key)]
)


# --------------------------------------------------
# HEALTH CHECKS
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": config.SERVICE_NAME
    }


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL no responde"
        )

    return {
        "status": "ready",
        "service": config.SERVICE_NAME
    }


# --------------------------------------------------
# REGISTRO DE TRABAJOS BATCH
# --------------------------------------------------

class BatchRunCreate(BaseModel):
    run_id: UUID
    report_date: date
    status: str = Field(min_length=1, max_length=30)
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    objects: list[str | dict[str, Any]] = Field(
        default_factory=list
    )


@protected.post(
    "/internal/batch-runs",
    status_code=status.HTTP_201_CREATED
)
def register_batch_run(
    batch: BatchRunCreate,
    db: Session = Depends(get_db)
):
    try:
        db.execute(
            text("""
                INSERT INTO batch_runs (
                    run_id,
                    report_date,
                    status,
                    started_at,
                    finished_at,
                    objects
                )
                VALUES (
                    CAST(:run_id AS UUID),
                    :report_date,
                    :status,
                    :started_at,
                    :finished_at,
                    CAST(:objects AS JSONB)
                )
            """),
            {
                "run_id": str(batch.run_id),
                "report_date": batch.report_date,
                "status": batch.status,
                "started_at": batch.started_at,
                "finished_at": batch.finished_at,
                "objects": json.dumps(batch.objects)
            }
        )

        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="La ejecucion Batch ya existe"
        )

    except SQLAlchemyError:
        db.rollback()
        logger.exception("batch_registration_failed")
        raise HTTPException(
            status_code=503,
            detail="No se pudo registrar la ejecucion Batch"
        )

    return {
        "run_id": str(batch.run_id),
        "status": batch.status
    }



# --------------------------------------------------
# FASE 7: CONSULTA GLOBAL DE BODEGAS
# --------------------------------------------------

@protected.get("/global/warehouses")
def get_global_warehouses(db: Session = Depends(get_db)):
    """Consulta el estado conocido de las bodegas."""

    try:
        rows = db.execute(
            text("""
                SELECT
                    warehouse_id,
                    last_seen_at,
                    last_event_at,
                    (
                        last_seen_at IS NULL
                        OR last_seen_at < NOW() - INTERVAL '90 seconds'
                    ) AS stale
                FROM warehouse_status
                ORDER BY warehouse_id
            """)
        ).mappings().all()

    except SQLAlchemyError:
        logger.exception("global_warehouses_query_failed")
        raise HTTPException(
            status_code=503,
            detail="No se pudo consultar el estado de las bodegas"
        )

    return {
        "count": len(rows),
        "warehouses": [dict(row) for row in rows]
    }



# --------------------------------------------------
# FASE 7: INVENTARIO GLOBAL POR SKU
# --------------------------------------------------

@protected.get("/global/inventory/{sku}")
def get_global_inventory(
    sku: str,
    db: Session = Depends(get_db)
):
    """Consulta el inventario consolidado por producto."""

    try:
        rows = db.execute(
            text("""
                SELECT
                    gi.sku,
                    gi.warehouse_id,
                    gi.quantity,
                    gi.reserved_quantity,
                    gi.quantity - gi.reserved_quantity
                        AS available_quantity,
                    gi.version,
                    gi.updated_at,
                    ws.last_seen_at,
                    (
                        ws.last_seen_at IS NULL
                        OR ws.last_seen_at < NOW() - INTERVAL '90 seconds'
                    ) AS stale
                FROM global_inventory gi
                LEFT JOIN warehouse_status ws
                    ON gi.warehouse_id = ws.warehouse_id
                WHERE gi.sku = :sku
                ORDER BY gi.warehouse_id
            """),
            {"sku": sku}
        ).mappings().all()

    except SQLAlchemyError:
        logger.exception("global_inventory_query_failed")
        raise HTTPException(
            status_code=503,
            detail="No se pudo consultar el inventario global"
        )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado en el inventario global"
        )

    total_quantity = sum(row["quantity"] for row in rows)
    total_reserved = sum(row["reserved_quantity"] for row in rows)

    return {
        "sku": sku,
        "total_quantity": total_quantity,
        "total_reserved": total_reserved,
        "total_available": total_quantity - total_reserved,
        "as_of": max(row["updated_at"] for row in rows),
        "warehouses": [
            {
                "warehouse_id": row["warehouse_id"],
                "quantity": row["quantity"],
                "reserved_quantity": row["reserved_quantity"],
                "available_quantity": row["available_quantity"],
                "version": row["version"],
                "updated_at": row["updated_at"],
                "last_seen_at": row["last_seen_at"],
                "stale": row["stale"]
            }
            for row in rows
        ]
    }



# --------------------------------------------------
# FASE 7: INVENTARIO GLOBAL PAGINADO
# --------------------------------------------------

@protected.get("/global/inventory")
def list_global_inventory(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Consulta el inventario consolidado por SKU con paginacion."""

    offset = (page - 1) * page_size

    try:
        total = db.execute(
            text("""
                SELECT COUNT(DISTINCT sku)
                FROM global_inventory
            """)
        ).scalar_one()

        rows = db.execute(
            text("""
                SELECT
                    gi.sku,
                    SUM(gi.quantity) AS total_quantity,
                    SUM(gi.reserved_quantity) AS total_reserved,
                    SUM(
                        gi.quantity - gi.reserved_quantity
                    ) AS total_available,
                    COUNT(*) AS warehouse_count,
                    COUNT(*) FILTER (
                        WHERE ws.last_seen_at IS NULL
                           OR ws.last_seen_at <
                              NOW() - INTERVAL '90 seconds'
                    ) AS stale_warehouses,
                    MAX(gi.updated_at) AS as_of
                FROM global_inventory gi
                LEFT JOIN warehouse_status ws
                    ON gi.warehouse_id = ws.warehouse_id
                GROUP BY gi.sku
                ORDER BY gi.sku
                LIMIT :limit OFFSET :offset
            """),
            {
                "limit": page_size,
                "offset": offset
            }
        ).mappings().all()

    except SQLAlchemyError:
        logger.exception("global_inventory_list_failed")
        raise HTTPException(
            status_code=503,
            detail="No se pudo consultar el inventario global"
        )

    return {
        "page": page,
        "page_size": page_size,
        "total_items": total,
        "total_pages": (total + page_size - 1) // page_size,
        "items": [dict(row) for row in rows]
    }


app.include_router(protected)
