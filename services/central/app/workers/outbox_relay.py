import logging

from sqlalchemy import text

from common.rabbit import connect, declare_topology, publish

from app import config
from app.domain.database import SessionLocal


logger = logging.getLogger(__name__)

POLL_INTERVAL = 0.5
MAX_BACKOFF = 30


def relay_pending_message(channel):
    """Publica el siguiente mensaje pendiente de Outbox."""

    with SessionLocal.begin() as db:

        row = db.execute(
            text("""
                SELECT id, event_id, exchange,
                       routing_key, payload
                FROM outbox
                WHERE published_at IS NULL
                ORDER BY id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """)
        ).mappings().first()

        if row is None:
            return False, False

        try:
            publish(
                row["payload"],
                exchange=row["exchange"],
                routing_key=row["routing_key"],
                channel=channel
            )

        except Exception:

            db.execute(
                text("""
                    UPDATE outbox
                    SET attempts = attempts + 1
                    WHERE id = :id
                """),
                {"id": row["id"]}
            )

            logger.exception(
                "central_outbox_publish_failed",
                extra={
                    "event_id": str(row["event_id"])
                }
            )

            return False, True

        db.execute(
            text("""
                UPDATE outbox
                SET published_at = NOW(),
                    attempts = attempts + 1
                WHERE id = :id
            """),
            {"id": row["id"]}
        )

        logger.info(
            "central_outbox_published",
            extra={
                "event_id": str(row["event_id"]),
                "event_type": row["payload"]["event_type"],
                "exchange": row["exchange"],
                "routing_key": row["routing_key"]
            }
        )

        return True, False


def run_outbox_relay(stop_event):

    failures = 0

    logger.info("central_outbox_relay_starting")

    while not stop_event.is_set():

        connection = None

        try:
            connection = connect(
                url=config.RABBITMQ_URL or None,
                attempts=3
            )

            channel = connection.channel()

            declare_topology(channel)

            logger.info("central_outbox_relay_ready")

            while not stop_event.is_set():

                connection.process_data_events(
                    time_limit=0
                )

                published, failed = relay_pending_message(
                    channel
                )

                if failed:
                    raise RuntimeError(
                        "No se pudo publicar mensaje de Outbox"
                    )

                failures = 0

                if not published:
                    stop_event.wait(POLL_INTERVAL)

        except Exception:

            logger.exception(
                "central_outbox_relay_failed"
            )

            delay = min(
                0.5 * (2 ** min(failures, 6)),
                MAX_BACKOFF
            )

            failures += 1

            stop_event.wait(delay)

        finally:

            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    logger.exception(
                        "central_outbox_connection_close_failed"
                    )

    logger.info("central_outbox_relay_stopped")
