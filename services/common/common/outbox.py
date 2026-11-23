"""Insert events into the warehouse outbox using the caller's transaction."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def add_event(
    session: Session,
    envelope: Mapping[str, Any] | Any,
    exchange: str,
    routing_key: str,
) -> str:
    """Insert an envelope without committing the active SQLAlchemy transaction."""

    if hasattr(envelope, "model_dump"):
        payload = envelope.model_dump(mode="json")
    elif isinstance(envelope, Mapping):
        payload = dict(envelope)
    else:
        raise TypeError("envelope debe ser un mapping o un modelo Pydantic")

    required = {
        "event_id",
        "event_type",
        "event_version",
        "occurred_at",
        "correlation_id",
        "source",
        "payload",
    }
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"Faltan campos del sobre: {', '.join(sorted(missing))}")

    event_id = str(payload["event_id"])
    session.execute(
        text(
            """
            INSERT INTO outbox (event_id, exchange, routing_key, payload)
            VALUES (
                CAST(:event_id AS UUID),
                :exchange,
                :routing_key,
                CAST(:payload AS JSONB)
            )
            """
        ),
        {
            "event_id": event_id,
            "exchange": exchange,
            "routing_key": routing_key,
            "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    )
    return event_id
