"""Proyeccion CQRS de inventario y heartbeats."""

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import text

from common.events import EventEnvelope
from common.rabbit import PermanentError
from app.domain.database import SessionLocal


class InventoryPayload(BaseModel):
    warehouse_id: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    quantity: int = Field(ge=0)
    reserved_quantity: int = Field(ge=0)
    version: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_stock(self):
        if self.reserved_quantity > self.quantity:
            raise ValueError("Las reservas superan el inventario")
        return self


class HeartbeatPayload(BaseModel):
    warehouse_id: str = Field(min_length=1)


def process_event(message: dict):
    """Procesa un evento y confirma sus cambios en PostgreSQL."""

    try:
        event = EventEnvelope.model_validate(message)
    except ValidationError as exc:
        raise PermanentError(f"Sobre inválido: {exc}") from exc

    if event.event_version != 1:
        raise PermanentError("Versión de evento no soportada")

    try:
        if event.event_type == "INVENTORY_UPDATED":
            data = InventoryPayload.model_validate(event.payload)
        elif event.event_type == "WAREHOUSE_HEARTBEAT":
            data = HeartbeatPayload.model_validate(event.payload)
        else:
            raise PermanentError("Tipo de evento no soportado")
    except ValidationError as exc:
        raise PermanentError(f"Payload inválido: {exc}") from exc

    # La transaccion incluye idempotencia y proyeccion.
    with SessionLocal.begin() as db:

        inserted = db.execute(
            text("""
                INSERT INTO processed_messages (message_id, consumer)
                VALUES (:event_id, 'central.projection')
                ON CONFLICT DO NOTHING
                RETURNING message_id
            """),
            {"event_id": event.event_id},
        ).scalar_one_or_none()

        # El mismo evento ya fue procesado.
        if inserted is None:
            return

        if event.event_type == "INVENTORY_UPDATED":
            db.execute(
                text("""
                    INSERT INTO global_inventory (
                        sku, warehouse_id, quantity,
                        reserved_quantity, version, updated_at
                    )
                    VALUES (
                        :sku, :warehouse_id, :quantity,
                        :reserved_quantity, :version, :occurred_at
                    )
                    ON CONFLICT (sku, warehouse_id)
                    DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        reserved_quantity = EXCLUDED.reserved_quantity,
                        version = EXCLUDED.version,
                        updated_at = EXCLUDED.updated_at
                    WHERE global_inventory.version < EXCLUDED.version
                """),
                {
                    **data.model_dump(),
                    "occurred_at": event.occurred_at,
                },
            )

            db.execute(
                text("""
                    INSERT INTO warehouse_status (
                        warehouse_id, last_event_at
                    )
                    VALUES (:warehouse_id, :occurred_at)
                    ON CONFLICT (warehouse_id)
                    DO UPDATE SET
                        last_event_at = GREATEST(
                            warehouse_status.last_event_at,
                            EXCLUDED.last_event_at
                        )
                """),
                {
                    "warehouse_id": data.warehouse_id,
                    "occurred_at": event.occurred_at,
                },
            )

        elif event.event_type == "WAREHOUSE_HEARTBEAT":
            db.execute(
                text("""
                    INSERT INTO warehouse_status (
                        warehouse_id, last_seen_at
                    )
                    VALUES (:warehouse_id, :occurred_at)
                    ON CONFLICT (warehouse_id)
                    DO UPDATE SET
                        last_seen_at = GREATEST(
                            warehouse_status.last_seen_at,
                            EXCLUDED.last_seen_at
                        )
                """),
                {
                    "warehouse_id": data.warehouse_id,
                    "occurred_at": event.occurred_at,
                },
            )
