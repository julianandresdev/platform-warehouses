from __future__ import annotations

from uuid import uuid4

import pytest

from app.alerts import advance_streak
from app.schemas import SensorReading, routing_key_for, validate_topic
from app.spool import SensorSpool


def reading(**overrides):
    values = {
        "event_id": uuid4(),
        "warehouse_id": "WH-001",
        "sensor_id": "sensor-0001",
        "sensor_type": "temperature",
        "value": 24.5,
        "sequence_number": 1,
        "timestamp": "2026-11-26T15:00:00Z",
    }
    values.update(overrides)
    return SensorReading.model_validate(values)


def test_sensor_payload_routes_to_warehouse_and_type():
    event = reading()
    assert routing_key_for(event) == "iot.WH-001.temperature"
    validate_topic("warehouses/WH-001/sensors/sensor-0001", event)


def test_sensor_topic_must_match_payload():
    with pytest.raises(ValueError, match="no coincide"):
        validate_topic("warehouses/WH-002/sensors/sensor-0001", reading())


def test_sensor_schema_rejects_non_positive_sequence_and_extra_fields():
    with pytest.raises(ValueError):
        reading(sequence_number=0)
    with pytest.raises(ValueError):
        reading(unexpected="value")


def test_spool_persists_pending_readings_and_monotonic_sequences(tmp_path):
    path = str(tmp_path / "sensor-spool.sqlite3")
    spool = SensorSpool(path)
    first = {"event_id": str(uuid4()), "sequence_number": 1, "warehouse_id": "WH-001"}
    first_row = spool.add("sensor-0001", first)
    assert spool.next_sequence("sensor-0001") == 2
    spool.close()

    reopened = SensorSpool(path)
    pending = reopened.pending()
    assert pending == [(first_row, "sensor-0001", 1, first)]
    reopened.delete(first_row)
    assert reopened.count() == 0
    assert reopened.next_sequence("sensor-0001") == 2
    reopened.close()


def test_alert_emits_once_after_three_consecutive_high_values():
    last, streak, active = 0, 0, False
    for sequence in (1, 2):
        last, streak, active, alert = advance_streak(sequence, 36, last, streak, active, 35)
        assert not alert
    last, streak, active, alert = advance_streak(3, 37, last, streak, active, 35)
    assert alert
    assert active
    last, streak, active, alert = advance_streak(4, 38, last, streak, active, 35)
    assert not alert
    assert active


def test_alert_streak_resets_on_gap_and_normal_reading():
    last, streak, active, _ = advance_streak(1, 38, 0, 0, False, 35)
    last, streak, active, alert = advance_streak(3, 38, last, streak, active, 35)
    assert (last, streak, alert) == (3, 1, False)
    last, streak, active, alert = advance_streak(4, 20, last, streak, active, 35)
    assert (last, streak, active, alert) == (4, 0, False, False)


def test_alert_ignores_late_sequences():
    assert advance_streak(4, 40, 5, 2, True, 35) == (5, 2, True, False)

