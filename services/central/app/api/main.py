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
    Header, HTTPException, status
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


app.include_router(protected)
