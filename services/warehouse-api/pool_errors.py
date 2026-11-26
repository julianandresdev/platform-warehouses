"""Respuesta 503 cuando no hay conexión libre en el pool (J-06, atasco visto en J-09)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

logger = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = "2"


def register_pool_error_handler(app: FastAPI) -> None:
    """Un request que espera una conexión más de ``DB_POOL_TIMEOUT`` responde 503, no 500."""

    @app.exception_handler(PoolTimeoutError)
    async def pool_timeout(request: Request, exc: PoolTimeoutError) -> JSONResponse:
        logger.warning("db_pool_exhausted", extra={"path": request.url.path})
        return JSONResponse(
            status_code=503,
            content={"detail": "Servicio saturado: no hay conexiones libres a la base de datos"},
            headers={"Retry-After": RETRY_AFTER_SECONDS},
        )
