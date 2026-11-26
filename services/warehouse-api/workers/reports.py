"""Generate inventory movement reports from queued report requests."""

from __future__ import annotations

import json
import logging
import signal
import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

import config
from common.events import EventEnvelope
from common.logging import configure_logging
from common import storage
from common.rabbit import PermanentError, connect, consume, declare_topology
from database import SessionLocal

logger = logging.getLogger(__name__)
stop_event = threading.Event()


class ReportParameters(BaseModel):
    start_at: AwareDatetime
    end_at: AwareDatetime

    def as_utc_naive(self, value: datetime) -> datetime:
        return value.astimezone(timezone.utc).replace(tzinfo=None)


class ReportRequested(BaseModel):
    job_id: UUID
    warehouse_id: str = Field(min_length=1, max_length=20)
    parameters: ReportParameters


def _report_result(session: Session, parameters: ReportParameters) -> dict[str, Any]:
    if parameters.end_at <= parameters.start_at:
        raise PermanentError("end_at debe ser posterior a start_at")

    bounds = {
        "start_at": parameters.as_utc_naive(parameters.start_at),
        "end_at": parameters.as_utc_naive(parameters.end_at),
        "warehouse_id": config.WAREHOUSE_ID,
    }
    by_type = session.execute(
        text(
            """
            SELECT type::text AS movement_type,
                   COUNT(*) AS movement_count,
                   COALESCE(SUM(ABS(quantity)), 0) AS units_moved
            FROM inventory_movements
            WHERE warehouse_id = :warehouse_id
              AND created_at >= :start_at
              AND created_at < :end_at
            GROUP BY type
            ORDER BY type::text
            """
        ),
        bounds,
    ).mappings().all()
    top_skus = session.execute(
        text(
            """
            SELECT p.sku,
                   COUNT(*) AS movement_count,
                   COALESCE(SUM(ABS(m.quantity)), 0) AS units_moved
            FROM inventory_movements AS m
            JOIN products AS p ON p.id = m.product_id
            WHERE m.warehouse_id = :warehouse_id
              AND m.created_at >= :start_at
              AND m.created_at < :end_at
            GROUP BY p.sku
            ORDER BY units_moved DESC, movement_count DESC, p.sku
            LIMIT 10
            """
        ),
        bounds,
    ).mappings().all()

    return {
        "warehouse_id": config.WAREHOUSE_ID,
        "range": {
            "start_at": parameters.start_at.astimezone(timezone.utc).isoformat(),
            "end_at": parameters.end_at.astimezone(timezone.utc).isoformat(),
        },
        "movements_by_type": [dict(row) for row in by_type],
        "top_skus": [dict(row) for row in top_skus],
    }


def report_object_key(job_id: UUID) -> str:
    return f"reports/jobs/{job_id}.json"


def store_report(
    job_id: UUID,
    result: dict[str, Any],
    correlation_id: str,
    *,
    client: Any = None,
) -> str:
    """Escribe el resultado en ``reports/jobs/<job_id>.json`` (J-08, punto 6).

    El objeto lleva el metadato ``correlation-id`` del evento que pidió el
    reporte. Devuelve la llave. Repetir el mismo trabajo reemplaza el objeto.
    """

    key = report_object_key(job_id)
    storage.put_json(
        key,
        {"job_id": str(job_id), **result},
        metadata={"correlation-id": correlation_id},
        client=client,
    )
    return key


def process_report_event(
    message: dict,
    session_factory: sessionmaker[Session] = SessionLocal,
) -> None:
    try:
        event = EventEnvelope.model_validate(message)
        if event.event_type != "REPORT_REQUESTED":
            raise PermanentError("El worker solo acepta REPORT_REQUESTED")
        request = ReportRequested.model_validate(event.payload)
    except ValidationError as exc:
        raise PermanentError(f"Mensaje de reporte inválido: {exc}") from exc
    if request.warehouse_id != config.WAREHOUSE_ID:
        raise PermanentError("El reporte pertenece a otra bodega")

    try:
        with session_factory.begin() as session:
            job = session.execute(
                text(
                    """
                    SELECT status, params
                    FROM report_jobs
                    WHERE job_id = :job_id
                    FOR UPDATE
                    """
                ),
                {"job_id": request.job_id},
            ).mappings().first()
            if job is None:
                raise PermanentError(f"No existe el reporte {request.job_id}")
            if job["status"] != "PROCESSING":
                logger.info(
                    "report_job_duplicate_ignored",
                    extra={"job_id": str(request.job_id), "status": job["status"]},
                )
                return

            try:
                parameters = ReportParameters.model_validate(job["params"])
            except ValidationError as exc:
                raise PermanentError(f"Parámetros de reporte inválidos: {exc}") from exc
            result = _report_result(session, parameters)
            if config.REPORTS_TO_S3:
                result["object_key"] = store_report(
                    request.job_id, result, event.correlation_id
                )
            session.execute(
                text(
                    """
                    UPDATE report_jobs
                    SET status = 'DONE', result = CAST(:result AS JSONB),
                        error = NULL, updated_at = now(), finished_at = now()
                    WHERE job_id = :job_id AND status = 'PROCESSING'
                    """
                ),
                {"job_id": request.job_id, "result": json.dumps(result)},
            )
    except PermanentError:
        raise
    except Exception as error:
        with session_factory.begin() as session:
            session.execute(
                text(
                    """
                    UPDATE report_jobs
                    SET status = 'FAILED', error = :error,
                        updated_at = now(), finished_at = now()
                    WHERE job_id = :job_id AND status = 'PROCESSING'
                    """
                ),
                {"job_id": request.job_id, "error": str(error)[:2000]},
            )
        logger.exception(
            "report_job_failed",
            extra={"job_id": str(request.job_id), "event_id": str(event.event_id)},
        )
        return

    logger.info(
        "report_job_completed",
        extra={"job_id": str(request.job_id), "event_id": str(event.event_id)},
    )


def _stop(signum, frame) -> None:
    logger.info("reports_worker_shutdown_requested", extra={"signal": signum})
    stop_event.set()


def run_worker() -> None:
    configure_logging("reports-worker", config.WAREHOUSE_ID, config.LOG_LEVEL)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    queue = f"{config.WAREHOUSE_ID.lower()}.reports"
    failures = 0
    connection = None

    while not stop_event.is_set():
        try:
            connection = connect(attempts=3)
            declare_topology(connection.channel(), warehouse_ids=(config.WAREHOUSE_ID,))
            logger.info("reports_worker_ready", extra={"queue": queue})
            consume(queue, process_report_event, connection=connection, stop_event=stop_event)
            failures = 0
        except Exception:
            if not stop_event.is_set():
                logger.exception("reports_worker_failed", extra={"queue": queue})
                failures += 1
                time.sleep(min(0.5 * (2 ** min(failures, 6)), 30))
        finally:
            if connection is not None and connection.is_open:
                connection.close()
            connection = None


if __name__ == "__main__":
    run_worker()
