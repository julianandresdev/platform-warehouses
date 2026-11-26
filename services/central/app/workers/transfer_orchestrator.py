import logging

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text

from common.events import EventEnvelope
from common.rabbit import PermanentError, connect, consume, declare_topology

from app import config
from app.domain.database import SessionLocal
from app.domain.saga import TransferStatus, get_transition
from app.domain.transfers import change_status, enqueue_command


logger = logging.getLogger(__name__)

CONSUMER = "central.transfer-orchestrator"
TIMEOUT_REASON = "RESERVATION_TIMEOUT"

SOURCE_EVENTS = {
    "STOCK_RESERVED",
    "STOCK_RESERVATION_FAILED",
    "RESERVATION_RELEASED",
    "TRANSFER_SHIPPED",
    "TRANSFER_SHIP_FAILED",
    "STOCK_RETURNED"
}

DESTINATION_EVENTS = {
    "TRANSFER_RECEIVED",
    "TRANSFER_RECEIVE_FAILED"
}


def command_exists(db, transfer_id, command):
    """Comprueba si el comando ya fue registrado."""

    return db.execute(
        text("""
            SELECT EXISTS (
                SELECT 1
                FROM outbox
                WHERE payload->>'event_type' = :command
                  AND payload->'payload'->>'transfer_id' = :id
            )
        """),
        {
            "id": str(transfer_id),
            "command": command
        }
    ).scalar_one()


def process_transfer_event(message):
    """Procesa un resultado enviado por una bodega."""

    event = EventEnvelope.model_validate(message)
    event_type = event.event_type
    payload = event.payload

    if event.event_version != 1:
        raise PermanentError("Version de evento no soportada")

    if event_type not in SOURCE_EVENTS | DESTINATION_EVENTS:
        raise PermanentError(f"Tipo de evento no soportado por la Saga: {event_type}")

    try:
        transfer_id = str(UUID(payload["transfer_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PermanentError("El evento de Saga no contiene un transfer_id válido") from exc

    with SessionLocal.begin() as db:

        # Bloquear la transferencia durante su procesamiento.
        row = db.execute(
            text("""
                SELECT *
                FROM transfers
                WHERE id = :id
                FOR UPDATE
            """),
            {"id": transfer_id}
        ).mappings().first()

        if row is None:
            logger.warning(
                "saga_transfer_not_found",
                extra={"transfer_id": transfer_id}
            )
            return

        transfer = dict(row)

        # Validar que el evento corresponde a la bodega correcta.
        expected_warehouse = (
            transfer["source_warehouse_id"]
            if event_type in SOURCE_EVENTS
            else transfer["destination_warehouse_id"]
        )

        if (
            payload.get("warehouse_id") != expected_warehouse
            or event.source != f"warehouse-{expected_warehouse}"
            or payload.get("sku") != transfer["sku"]
            or type(payload.get("quantity")) is not int
            or payload["quantity"] != transfer["quantity"]
        ):
            raise PermanentError(
                "El evento no corresponde a la transferencia"
            )

        # Registrar el mensaje para garantizar idempotencia.
        inserted = db.execute(
            text("""
                INSERT INTO processed_messages (
                    message_id, consumer
                )
                VALUES (:message_id, :consumer)
                ON CONFLICT DO NOTHING
                RETURNING message_id
            """),
            {
                "message_id": str(event.event_id),
                "consumer": CONSUMER
            }
        ).scalar_one_or_none()

        if inserted is None:
            logger.info(
                "saga_duplicate_event",
                extra={"transfer_id": transfer_id}
            )
            return

        # Recuperar el correlation ID original de la Saga.
        correlation_id = db.execute(
            text("""
                SELECT correlation_id
                FROM transfer_history
                WHERE transfer_id = :id
                ORDER BY id
                LIMIT 1
            """),
            {"id": transfer_id}
        ).scalar_one()

        correlation_id = correlation_id or event.correlation_id

        # Manejar reservas recibidas despues del deadline.
        if event_type == "STOCK_RESERVED":

            if (
                transfer["status"] == "RESERVING_SOURCE"
                and transfer["deadline"] is not None
                and transfer["deadline"] <= datetime.now(timezone.utc)
            ):
                transfer = change_status(
                    db,
                    transfer,
                    TransferStatus.FAILED,
                    correlation_id,
                    TIMEOUT_REASON
                )

            if (
                transfer["status"] == "FAILED"
                and transfer["reason"] == TIMEOUT_REASON
            ):
                if not command_exists(
                    db,
                    transfer_id,
                    "RELEASE_RESERVATION"
                ):
                    enqueue_command(
                        db,
                        transfer,
                        "RELEASE_RESERVATION",
                        "source",
                        correlation_id
                    )

                    logger.warning(
                        "saga_late_reservation",
                        extra={"transfer_id": transfer_id}
                    )

                return

        # Validar que las compensaciones fueron solicitadas.
        compensation_commands = {
            "STOCK_RETURNED": "RETURN_STOCK",
            "RESERVATION_RELEASED": "RELEASE_RESERVATION"
        }

        if event_type in compensation_commands:
            if not command_exists(
                db,
                transfer_id,
                compensation_commands[event_type]
            ):
                logger.warning(
                    "saga_unexpected_compensation",
                    extra={"transfer_id": transfer_id}
                )
                return

        # Consultar la maquina de estados.
        transition = get_transition(
            transfer["status"],
            event_type
        )

        if transition is None:
            logger.info(
                "saga_event_ignored",
                extra={
                    "transfer_id": transfer_id,
                    "status": transfer["status"],
                    "event_type": event_type
                }
            )
            return

        # Aplicar todos los cambios de estado.
        for new_status in transition.states:

            transfer = change_status(
                db,
                transfer,
                new_status,
                correlation_id,
                payload.get("reason")
            )

        # Registrar el siguiente comando en Outbox.
        if transition.command:
            enqueue_command(
                db,
                transfer,
                transition.command,
                transition.target,
                correlation_id
            )

    logger.info(
        "saga_transition_completed",
        extra={
            "transfer_id": transfer_id,
            "event_type": event_type,
            "status": transfer["status"]
        }
    )


def run_transfer_orchestrator(stop_event):

    logger.info("saga_orchestrator_starting")

    while not stop_event.is_set():

        connection = None

        try:
            connection = connect(
                url=config.RABBITMQ_URL or None,
                attempts=3
            )

            declare_topology(connection.channel())

            logger.info("saga_orchestrator_ready")

            consume(
                queue=CONSUMER,
                handler=process_transfer_event,
                connection=connection,
                stop_event=stop_event
            )

        except Exception:
            if not stop_event.is_set():
                logger.exception(
                    "saga_orchestrator_failed"
                )
                stop_event.wait(3)

        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    logger.exception(
                        "saga_connection_close_failed"
                    )

    logger.info("saga_orchestrator_stopped")
