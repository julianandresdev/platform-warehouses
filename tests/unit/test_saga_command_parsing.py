"""Pruebas unitarias del parseo de comandos y de CHAOS_FAIL_STEP (J-07)."""

from __future__ import annotations

import uuid

import pytest

from workers.commands import (
    ChaosError,
    InvalidCommandError,
    chaos_point,
    parse_command,
)


def message(event_type="RESERVE_STOCK", **payload):
    base = {
        "transfer_id": str(uuid.uuid4()),
        "warehouse_id": "WH-001",
        "sku": "P-001",
        "quantity": 30,
        "deadline": "2026-11-24T15:00:30.123456Z",
    }
    base.update(payload)
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": "2026-11-24T15:00:00Z",
        "correlation_id": "COR-1",
        "source": "central",
        "payload": {k: v for k, v in base.items() if v is not None},
    }


def test_parse_reserve_stock_with_deadline():
    command = parse_command(message())
    assert command.event_type == "RESERVE_STOCK"
    assert command.quantity == 30
    assert command.deadline.tzinfo is not None
    assert command.reference == f"transfer:{command.transfer_id}"


def test_reserve_requires_deadline():
    with pytest.raises(InvalidCommandError):
        parse_command(message(deadline=None))


def test_other_commands_do_not_need_deadline():
    command = parse_command(message("SHIP_TRANSFER", deadline=None))
    assert command.deadline is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": 0},
        {"quantity": -1},
        {"quantity": "30"},
        {"quantity": True},
        {"transfer_id": "no-uuid"},
        {"sku": ""},
        {"deadline": "mañana"},
        {"deadline": "2026-11-24T15:00:30"},
    ],
)
def test_invalid_payloads(overrides):
    with pytest.raises(InvalidCommandError):
        parse_command(message(**overrides))


def test_unknown_command_type():
    with pytest.raises(InvalidCommandError):
        parse_command(message("DELETE_EVERYTHING"))


def test_missing_envelope_field():
    data = message()
    del data["correlation_id"]
    with pytest.raises(InvalidCommandError):
        parse_command(data)


@pytest.mark.parametrize(
    "setting, command, step, fails",
    [
        ("", "RESERVE_STOCK", "before_commit", False),
        ("before_commit", "RESERVE_STOCK", "before_commit", True),
        ("before_commit", "RESERVE_STOCK", "after_commit", False),
        ("*:after_commit", "SHIP_TRANSFER", "after_commit", True),
        ("SHIP_TRANSFER:after_commit", "RESERVE_STOCK", "after_commit", False),
        ("RESERVE_STOCK:x, SHIP_TRANSFER:before_commit", "SHIP_TRANSFER", "before_commit", True),
    ],
)
def test_chaos_point(setting, command, step, fails):
    if fails:
        with pytest.raises(ChaosError):
            chaos_point(command, step, setting)
    else:
        chaos_point(command, step, setting)
