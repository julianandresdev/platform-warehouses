"""Asynchronous Redis invalidation consumer for one warehouse."""

from __future__ import annotations

import logging
import signal
import threading
import time

import cache
import config
from common.events import EventEnvelope
from common.logging import configure_logging
from common.rabbit import connect, consume, declare_topology

logger = logging.getLogger(__name__)
stop_event = threading.Event()


def handle_invalidation(message: dict) -> None:
    event = EventEnvelope.model_validate(message)
    if event.event_type != "INVENTORY_UPDATED":
        raise ValueError("El worker solo acepta INVENTORY_UPDATED")

    warehouse_id = event.payload.get("warehouse_id")
    sku = event.payload.get("sku")
    if warehouse_id != config.WAREHOUSE_ID or not isinstance(sku, str) or not sku:
        raise ValueError("El evento no corresponde a esta bodega o no contiene SKU")

    cache.invalidate_inventory(sku, raise_on_error=True)
    logger.info(
        "cache_invalidation_completed",
        extra={"event_id": str(event.event_id), "sku": sku},
    )


def _stop(signum, frame) -> None:
    logger.info("cache_invalidation_shutdown_requested", extra={"signal": signum})
    stop_event.set()


def run_worker() -> None:
    configure_logging("cache-invalidation-worker", config.WAREHOUSE_ID, config.LOG_LEVEL)
    if config.CACHE_INVALIDATION != "async":
        logger.info(
            "cache_invalidation_worker_disabled",
            extra={"mode": config.CACHE_INVALIDATION},
        )
        return

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    queue = f"{config.WAREHOUSE_ID.lower()}.cache-invalidation"
    failures = 0
    connection = None

    while not stop_event.is_set():
        try:
            connection = connect(attempts=3)
            declare_topology(connection.channel(), warehouse_ids=(config.WAREHOUSE_ID,))
            logger.info("cache_invalidation_worker_ready", extra={"queue": queue})
            consume(queue, handle_invalidation, connection=connection, stop_event=stop_event)
            failures = 0
        except Exception:
            if not stop_event.is_set():
                logger.exception("cache_invalidation_worker_failed", extra={"queue": queue})
                failures += 1
                time.sleep(min(0.5 * (2 ** min(failures, 6)), 30))
        finally:
            if connection is not None and connection.is_open:
                connection.close()
            connection = None


if __name__ == "__main__":
    run_worker()
