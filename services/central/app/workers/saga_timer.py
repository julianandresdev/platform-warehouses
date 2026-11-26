import logging

from sqlalchemy import text

from common.correlation import generate_correlation_id

from app.domain.database import SessionLocal
from app.domain.saga import TransferStatus
from app.domain.transfers import change_status
from app.workers.transfer_orchestrator import TIMEOUT_REASON


logger = logging.getLogger(__name__)

CHECK_INTERVAL = 5


# --------------------------------------------------
# RESERVAS VENCIDAS
# --------------------------------------------------

def check_expired_reservations():

    expired = []

    with SessionLocal.begin() as db:

        rows = db.execute(
            text("""
                SELECT *
                FROM transfers
                WHERE status = 'RESERVING_SOURCE'
                  AND deadline <= NOW()
                ORDER BY deadline
                LIMIT 100
                FOR UPDATE SKIP LOCKED
            """)
        ).mappings().all()

        for row in rows:

            transfer = dict(row)

            correlation_id = db.execute(
                text("""
                    SELECT correlation_id
                    FROM transfer_history
                    WHERE transfer_id = :id
                    ORDER BY id
                    LIMIT 1
                """),
                {"id": transfer["id"]}
            ).scalar_one_or_none()

            change_status(
                db,
                transfer,
                TransferStatus.FAILED,
                correlation_id or generate_correlation_id(),
                TIMEOUT_REASON
            )

            expired.append(str(transfer["id"]))

    for transfer_id in expired:

        logger.warning(
            "saga_reservation_timeout",
            extra={"transfer_id": transfer_id}
        )

    return len(expired)


# --------------------------------------------------
# DESTINOS PENDIENTES
# --------------------------------------------------

def check_pending_destinations(alerted):

    with SessionLocal() as db:

        rows = db.execute(
            text("""
                SELECT
                    id,
                    destination_warehouse_id,
                    EXTRACT(
                        EPOCH FROM (NOW() - updated_at)
                    ) AS pending_seconds
                FROM transfers
                WHERE status = 'DESTINATION_PENDING'
                  AND updated_at <=
                      NOW() - INTERVAL '5 minutes'
            """)
        ).mappings().all()

    active = {str(row["id"]) for row in rows}

    alerted.intersection_update(active)

    for row in rows:

        transfer_id = str(row["id"])

        if transfer_id in alerted:
            continue

        logger.warning(
            "saga_destination_pending_alert",
            extra={
                "transfer_id": transfer_id,
                "warehouse_id": row[
                    "destination_warehouse_id"
                ],
                "pending_seconds": float(
                    row["pending_seconds"]
                )
            }
        )

        alerted.add(transfer_id)


# --------------------------------------------------
# TEMPORIZADOR
# --------------------------------------------------

def run_saga_timer(stop_event):

    alerted = set()

    logger.info("saga_timer_ready")

    while not stop_event.is_set():

        try:
            check_expired_reservations()
            check_pending_destinations(alerted)

        except Exception:
            logger.exception("saga_timer_failed")

        stop_event.wait(CHECK_INTERVAL)

    logger.info("saga_timer_stopped")
