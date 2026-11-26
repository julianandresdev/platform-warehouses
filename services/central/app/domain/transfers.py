import json

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.saga import TransferStatus, TERMINAL_STATES


class IdempotencyConflict(Exception):
    """La misma llave fue utilizada con datos diferentes."""


# --------------------------------------------------
# OUTBOX
# --------------------------------------------------

def enqueue_message(
    db: Session,
    exchange: str,
    routing_key: str,
    event_type: str,
    payload: dict,
    correlation_id: str
):
    event_id = str(uuid4())

    envelope = {
        "event_id": event_id,
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": datetime.now(timezone.utc)
            .isoformat().replace("+00:00", "Z"),
        "correlation_id": correlation_id,
        "source": "central",
        "payload": payload
    }

    db.execute(
        text("""
            INSERT INTO outbox (
                event_id, exchange, routing_key, payload
            )
            VALUES (
                :event_id, :exchange, :routing_key,
                CAST(:payload AS JSONB)
            )
        """),
        {
            "event_id": event_id,
            "exchange": exchange,
            "routing_key": routing_key,
            "payload": json.dumps(envelope)
        }
    )

    return event_id


# --------------------------------------------------
# HISTORIAL
# --------------------------------------------------

def record_history(
    db: Session,
    transfer_id,
    previous_status,
    new_status,
    correlation_id,
    reason=None
):
    db.execute(
        text("""
            INSERT INTO transfer_history (
                transfer_id, previous_status,
                new_status, correlation_id, reason
            )
            VALUES (
                :transfer_id, :previous_status,
                :new_status, :correlation_id, :reason
            )
        """),
        {
            "transfer_id": transfer_id,
            "previous_status": previous_status,
            "new_status": new_status,
            "correlation_id": correlation_id,
            "reason": reason
        }
    )


# --------------------------------------------------
# CAMBIO DE ESTADO
# --------------------------------------------------

def change_status(
    db: Session,
    transfer: dict,
    new_status: TransferStatus,
    correlation_id: str,
    reason=None
):
    previous = transfer["status"]
    reason = reason if reason is not None else transfer["reason"]

    row = db.execute(
        text("""
            UPDATE transfers
            SET status = :new_status,
                reason = :reason,
                updated_at = NOW(),
                completed_at = CASE
                    WHEN :terminal THEN NOW()
                    ELSE NULL
                END
            WHERE id = :id
              AND status = :previous
            RETURNING *
        """),
        {
            "id": transfer["id"],
            "previous": previous,
            "new_status": new_status.value,
            "reason": reason,
            "terminal": new_status in TERMINAL_STATES
        }
    ).mappings().one()

    record_history(
        db,
        transfer["id"],
        previous,
        new_status.value,
        correlation_id,
        reason
    )

    enqueue_message(
        db,
        "central.events",
        "central.transfer.status_changed",
        "TRANSFER_STATUS_CHANGED",
        {
            "transfer_id": str(transfer["id"]),
            "from": previous,
            "to": new_status.value
        },
        correlation_id
    )

    return dict(row)


# --------------------------------------------------
# COMANDOS DE TRANSFERENCIA
# --------------------------------------------------

def enqueue_command(
    db: Session,
    transfer: dict,
    command: str,
    target: str,
    correlation_id: str
):
    if target == "source":
        warehouse_id = transfer["source_warehouse_id"]
    elif target == "destination":
        warehouse_id = transfer["destination_warehouse_id"]
    else:
        raise ValueError("Destino de comando invalido")

    payload = {
        "transfer_id": str(transfer["id"]),
        "warehouse_id": warehouse_id,
        "sku": transfer["sku"],
        "quantity": transfer["quantity"]
    }

    if command == "RESERVE_STOCK":
        payload["deadline"] = (
            transfer["deadline"]
            .astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    return enqueue_message(
        db,
        "warehouse.commands",
        warehouse_id,
        command,
        payload,
        correlation_id
    )


# --------------------------------------------------
# CREACION DE TRANSFERENCIAS
# --------------------------------------------------

def create_transfer(
    db: Session,
    idempotency_key: str,
    source_warehouse_id: str,
    destination_warehouse_id: str,
    sku: str,
    quantity: int,
    correlation_id: str
):
    data = {
        "source_warehouse_id": source_warehouse_id,
        "destination_warehouse_id": destination_warehouse_id,
        "sku": sku,
        "quantity": quantity
    }

    row = db.execute(
        text("""
            INSERT INTO transfers (
                id, idempotency_key,
                source_warehouse_id,
                destination_warehouse_id,
                sku, quantity, status, deadline
            )
            VALUES (
                :id, :idempotency_key,
                :source_warehouse_id,
                :destination_warehouse_id,
                :sku, :quantity, 'REQUESTED',
                NOW() + INTERVAL '30 seconds'
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING *
        """),
        {
            "id": str(uuid4()),
            "idempotency_key": idempotency_key,
            **data
        }
    ).mappings().first()

    # Si la transferencia ya existe, no repetirla.
    if row is None:
        existing = db.execute(
            text("""
                SELECT *
                FROM transfers
                WHERE idempotency_key = :key
            """),
            {"key": idempotency_key}
        ).mappings().one()

        if any(existing[key] != value
               for key, value in data.items()):
            raise IdempotencyConflict(
                "Idempotency-Key utilizada con otros datos"
            )

        return dict(existing), False

    transfer = dict(row)

    record_history(
        db,
        transfer["id"],
        None,
        TransferStatus.REQUESTED.value,
        correlation_id
    )

    enqueue_command(
        db,
        transfer,
        "RESERVE_STOCK",
        "source",
        correlation_id
    )

    transfer = change_status(
        db,
        transfer,
        TransferStatus.RESERVING_SOURCE,
        correlation_id
    )

    return transfer, True
