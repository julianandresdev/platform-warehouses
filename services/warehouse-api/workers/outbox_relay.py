"""Relay transactional outbox rows to RabbitMQ and publish warehouse heartbeats."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

import config
from common.events import new_event
from common.logging import configure_logging
from common.rabbit import connect, declare_topology, publish
from database import SessionLocal

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 30
MAX_BACKOFF_SECONDS = 30
OUTBOX_BATCH_SIZE = 100


def relay_pending_batch(
    session_factory: sessionmaker[Session],
    channel: Any,
    *,
    batch_size: int = OUTBOX_BATCH_SIZE,
    publisher: Callable[..., None] = publish,
) -> tuple[int, bool]:
    """Publish one locked batch; return (published rows, whether publish failed)."""

    published = 0
    failed = False
    with session_factory() as session:
        with session.begin():
            rows = (
                session.execute(
                    text(
                        """
                        SELECT id, event_id, exchange, routing_key, payload, attempts
                        FROM outbox
                        WHERE published_at IS NULL
                        ORDER BY id
                        FOR UPDATE SKIP LOCKED
                        LIMIT :batch_size
                        """
                    ),
                    {"batch_size": batch_size},
                )
                .mappings()
                .all()
            )

            for row in rows:
                try:
                    publisher(
                        row["payload"],
                        row["exchange"],
                        row["routing_key"],
                        channel=channel,
                    )
                except Exception:
                    session.execute(
                        text("UPDATE outbox SET attempts = attempts + 1 WHERE id = :id"),
                        {"id": row["id"]},
                    )
                    logger.exception(
                        "outbox_publish_failed",
                        extra={"event_id": str(row["event_id"]), "outbox_id": row["id"]},
                    )
                    failed = True
                    break

                session.execute(
                    text(
                        """
                        UPDATE outbox
                        SET published_at = now(), attempts = attempts + 1
                        WHERE id = :id
                        """
                    ),
                    {"id": row["id"]},
                )
                published += 1

    return published, failed


def publish_heartbeat(channel: Any, warehouse_id: str) -> None:
    envelope = new_event(
        event_type="WAREHOUSE_HEARTBEAT",
        payload={"warehouse_id": warehouse_id},
        source=f"warehouse-{warehouse_id}",
    )
    publish(
        envelope,
        exchange="warehouse.events",
        routing_key=f"warehouse.{warehouse_id}.heartbeat",
        channel=channel,
    )
    logger.info(
        "warehouse_heartbeat_published",
        extra={"warehouse_id": warehouse_id, "event_id": str(envelope.event_id)},
    )


def run_worker() -> None:
    warehouse_id = config.WAREHOUSE_ID
    configure_logging("warehouse-worker", warehouse_id, config.LOG_LEVEL)
    connection = None
    channel = None
    failures = 0
    next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS

    try:
        while True:
            try:
                if connection is None or not connection.is_open:
                    connection = connect()
                    channel = connection.channel()
                    declare_topology(channel, warehouse_ids=(warehouse_id,))

                published, failed = relay_pending_batch(SessionLocal, channel)
                if failed:
                    raise RuntimeError("El relay no pudo publicar el siguiente mensaje")

                now = time.monotonic()
                if now >= next_heartbeat:
                    publish_heartbeat(channel, warehouse_id)
                    next_heartbeat = now + HEARTBEAT_INTERVAL_SECONDS

                failures = 0
                if published == 0:
                    time.sleep(POLL_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                break
            except Exception:
                logger.exception("outbox_worker_iteration_failed")
                if connection is not None and connection.is_open:
                    connection.close()
                connection = None
                channel = None
                delay = min(0.5 * (2**failures), MAX_BACKOFF_SECONDS)
                failures += 1
                logger.warning(
                    "outbox_worker_backoff",
                    extra={"delay_seconds": delay, "consecutive_failures": failures},
                )
                time.sleep(delay)
    finally:
        if connection is not None and connection.is_open:
            connection.close()


if __name__ == "__main__":
    run_worker()
