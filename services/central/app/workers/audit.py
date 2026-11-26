"""Idempotent central audit consumer."""

from __future__ import annotations

import json
import logging
import signal
import threading
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from common.events import EventEnvelope
from common.logging import configure_logging
from common.rabbit import connect, consume, declare_topology

from app import config
from app.domain.database import SessionLocal

logger = logging.getLogger(__name__)
stop_event = threading.Event()


def process_audit_event(
    message: dict[str, Any],
    session_factory: sessionmaker[Session] = SessionLocal,
) -> None:
    event = EventEnvelope.model_validate(message)
    with session_factory.begin() as session:
        result = session.execute(
            text(
                """
                INSERT INTO audit_events (
                    event_id, event_type, source, correlation_id,
                    payload, occurred_at
                )
                VALUES (
                    :event_id, :event_type, :source, :correlation_id,
                    CAST(:payload AS JSONB), :occurred_at
                )
                ON CONFLICT (event_id) DO NOTHING
                """
            ),
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "source": event.source,
                "correlation_id": event.correlation_id,
                    "payload": json.dumps(event.payload, ensure_ascii=False),
                "occurred_at": event.occurred_at,
            },
        )
    logger.info(
        "audit_event_processed",
        extra={"event_id": str(event.event_id), "inserted": result.rowcount == 1},
    )


def _stop(signum, frame) -> None:
    logger.info("audit_worker_shutdown_requested", extra={"signal": signum})
    stop_event.set()


def run_worker() -> None:
    configure_logging("central-audit-worker", None, config.LOG_LEVEL)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    failures = 0
    connection = None

    while not stop_event.is_set():
        try:
            connection = connect(url=config.RABBITMQ_URL or None, attempts=3)
            declare_topology(connection.channel())
            logger.info("audit_worker_ready", extra={"queue": "central.audit"})
            consume(
                "central.audit", process_audit_event,
                connection=connection, stop_event=stop_event,
            )
            failures = 0
        except Exception:
            if not stop_event.is_set():
                logger.exception("audit_worker_failed")
                failures += 1
                time.sleep(min(0.5 * (2 ** min(failures, 6)), 30))
        finally:
            if connection is not None and connection.is_open:
                connection.close()
            connection = None


if __name__ == "__main__":
    run_worker()
