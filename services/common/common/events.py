"""Sobre común de eventos y comandos (docs/events.md)."""

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_serializer, field_validator

from common.correlation import generate_correlation_id, get_correlation_id


class EventEnvelope(BaseModel):
    event_id: uuid.UUID
    event_type: str = Field(min_length=1, pattern=r"^[A-Z][A-Z0-9_]*$")
    event_version: int = Field(default=1, ge=1)
    occurred_at: datetime
    correlation_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    payload: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def _must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at debe incluir zona horaria (UTC)")
        return value.astimezone(timezone.utc)

    @field_serializer("event_id")
    def _serialize_id(self, value: uuid.UUID) -> str:
        return str(value)

    @field_serializer("occurred_at")
    def _serialize_occurred_at(self, value: datetime) -> str:
        # ISO 8601 en UTC terminado en Z, como exige el contrato.
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def to_json(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes | str) -> "EventEnvelope":
        return cls.model_validate_json(data)


def new_event(
    event_type: str,
    payload: dict[str, Any],
    source: str,
    correlation_id: str | None = None,
    event_version: int = 1,
) -> EventEnvelope:
    """Crea un sobre nuevo con UUID v4 y fecha UTC.

    Sin correlation_id explícito usa el del request en curso; si tampoco hay,
    genera uno.
    """
    return EventEnvelope(
        event_id=uuid.uuid4(),
        event_type=event_type,
        event_version=event_version,
        occurred_at=datetime.now(timezone.utc).replace(microsecond=0),
        correlation_id=correlation_id or get_correlation_id() or generate_correlation_id(),
        source=source,
        payload=payload,
    )
