
import logging
import signal
import threading

from datetime import datetime, timezone
from prometheus_client import Gauge, start_http_server
from common.events import EventEnvelope
from sqlalchemy import text

from common.logging import configure_logging
from common.rabbit import connect, consume, declare_topology

from app import config
from app.domain.database import SessionLocal
from app.workers.projection import process_event
from app.workers.outbox_relay import run_outbox_relay
from app.workers.transfer_orchestrator import run_transfer_orchestrator
from app.workers.saga_timer import run_saga_timer


configure_logging("central-worker", None, config.LOG_LEVEL)

logger = logging.getLogger("central-worker")
stop_event = threading.Event()

projection_lag_seconds = Gauge(
    "projection_lag_seconds",
    "Seconds between event occurrence and successful processing",
    ["warehouse_id"]
)


def handle_projected_event(message):
    process_event(message)
    event = EventEnvelope.model_validate(message)
    warehouse_id = event.payload.get("warehouse_id", "unknown")
    lag = max(
        0.0,
        (datetime.now(timezone.utc) - event.occurred_at).total_seconds()
    )
    projection_lag_seconds.labels(
        warehouse_id=warehouse_id
    ).set(lag)



def handle_shutdown(signum, frame):
    logger.info(
        "central_worker_shutdown_requested",
        extra={"signal": signum}
    )
    stop_event.set()


def main():
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("central_worker_starting")

    with SessionLocal() as db:
        db.execute(text("SELECT 1"))

    logger.info("central_worker_database_ready")
    start_http_server(9101, addr="0.0.0.0")

    relay_thread = threading.Thread(
        target=run_outbox_relay,
        args=(stop_event,),
        name="central-outbox-relay",
        daemon=True
    )

    relay_thread.start()

    saga_thread = threading.Thread(
        target=run_transfer_orchestrator,
        args=(stop_event,),
        name="central-saga-orchestrator",
        daemon=True
    )

    saga_thread.start()

    timer_thread = threading.Thread(
        target=run_saga_timer,
        args=(stop_event,),
        name="central-saga-timer",
        daemon=True
    )

    timer_thread.start()

    while not stop_event.is_set():
        connection = None

        try:
            connection = connect(
                url=config.RABBITMQ_URL or None,
                attempts=3
            )

            declare_topology(connection.channel())

            logger.info("central_projection_consumer_ready")

            consume(
                queue="central.projection",
                handler=handle_projected_event,
                connection=connection,
                stop_event=stop_event
            )

        except Exception:
            if not stop_event.is_set():
                logger.exception("central_worker_connection_failed")
                stop_event.wait(3)

        finally:
            if connection is not None and connection.is_open:
                connection.close()

    relay_thread.join(timeout=5)
    saga_thread.join(timeout=5)
    timer_thread.join(timeout=5)

    logger.info("central_worker_stopped")


if __name__ == "__main__":
    main()
