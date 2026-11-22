import json
import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from common.correlation import reset_correlation_id, set_correlation_id
from common.events import EventEnvelope, new_event


def test_new_event_tiene_los_campos_del_contrato():
    ev = new_event("INVENTORY_UPDATED", {"sku": "P-001"}, "warehouse-WH-001", correlation_id="COR-TEST")
    data = json.loads(ev.to_json())

    assert set(data) == {
        "event_id", "event_type", "event_version", "occurred_at",
        "correlation_id", "source", "payload",
    }
    assert uuid.UUID(data["event_id"]).version == 4
    assert data["event_version"] == 1
    assert data["correlation_id"] == "COR-TEST"
    assert data["source"] == "warehouse-WH-001"
    assert data["payload"] == {"sku": "P-001"}


def test_occurred_at_es_utc_con_z():
    data = json.loads(new_event("X_Y", {}, "s").to_json())
    assert data["occurred_at"].endswith("Z")
    datetime.strptime(data["occurred_at"], "%Y-%m-%dT%H:%M:%SZ")


def test_usa_el_correlation_id_del_contexto():
    token = set_correlation_id("COR-CTX")
    try:
        assert new_event("A", {}, "s").correlation_id == "COR-CTX"
    finally:
        reset_correlation_id(token)


def test_genera_correlation_id_si_no_hay():
    assert new_event("A", {}, "s").correlation_id.startswith("COR-")


def test_ida_y_vuelta_json():
    ev = new_event("STOCK_RESERVED", {"quantity": 3}, "warehouse-WH-002")
    assert EventEnvelope.from_json(ev.to_json()) == ev


def test_event_ids_distintos():
    assert new_event("A", {}, "s").event_id != new_event("A", {}, "s").event_id


@pytest.mark.parametrize("bad_type", ["", "inventory_updated", "1ABC"])
def test_rechaza_event_type_invalido(bad_type):
    with pytest.raises(ValidationError):
        new_event(bad_type, {}, "s")


def test_rechaza_fecha_sin_zona_horaria():
    raw = {
        "event_id": str(uuid.uuid4()), "event_type": "A", "event_version": 1,
        "occurred_at": "2026-11-18T15:00:00", "correlation_id": "c",
        "source": "s", "payload": {},
    }
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(raw)


def test_rechaza_json_sin_campos_requeridos():
    with pytest.raises(ValidationError):
        EventEnvelope.from_json(b'{"event_type": "A"}')
