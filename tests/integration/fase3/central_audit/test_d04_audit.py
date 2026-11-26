"""Integration coverage for idempotent central audit writes."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "services" / "central"))
sys.path.insert(0, str(REPO / "services" / "common"))


def test_audit_event_is_deduplicated_by_event_id():
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL debe apuntar a la base central")

    from app.domain.database import SessionLocal
    from app.workers.audit import process_audit_event
    from common.events import new_event
    from sqlalchemy import text

    event = new_event(
        "INVENTORY_UPDATED",
        {"warehouse_id": "WH-001", "sku": f"D04-{uuid.uuid4().hex}"},
        source="warehouse-WH-001",
        correlation_id="D04-AUDIT-TEST",
    )
    message = event.model_dump(mode="json")
    try:
        process_audit_event(message)
        process_audit_event(message)
        with SessionLocal() as session:
            count = session.execute(
                text("SELECT COUNT(*) FROM audit_events WHERE event_id = :event_id"),
                {"event_id": event.event_id},
            ).scalar_one()
        assert count == 1
    finally:
        with SessionLocal.begin() as session:
            session.execute(
                text("DELETE FROM audit_events WHERE event_id = :event_id"),
                {"event_id": event.event_id},
            )
