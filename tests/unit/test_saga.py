import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "services/central")
)

from app.domain.saga import (
    TransferStatus,
    TERMINAL_STATES,
    get_transition
)


# ==================================================
# TRANSICIONES VALIDAS
# ==================================================

@pytest.mark.parametrize(
    "current,event,states,command,target",
    [
        (
            "RESERVING_SOURCE",
            "STOCK_RESERVED",
            ("SOURCE_RESERVED",),
            "SHIP_TRANSFER",
            "source"
        ),
        (
            "RESERVING_SOURCE",
            "STOCK_RESERVATION_FAILED",
            ("FAILED",),
            None,
            None
        ),
        (
            "SOURCE_RESERVED",
            "TRANSFER_SHIPPED",
            ("IN_TRANSIT", "DESTINATION_PENDING"),
            "RECEIVE_TRANSFER",
            "destination"
        ),
        (
            "DESTINATION_PENDING",
            "TRANSFER_RECEIVED",
            ("DESTINATION_RECEIVED", "COMPLETED"),
            None,
            None
        ),
        (
            "DESTINATION_PENDING",
            "TRANSFER_RECEIVE_FAILED",
            ("COMPENSATING",),
            "RETURN_STOCK",
            "source"
        ),
        (
            "COMPENSATING",
            "STOCK_RETURNED",
            ("CANCELLED",),
            None,
            None
        ),
        (
            "COMPENSATING",
            "RESERVATION_RELEASED",
            ("CANCELLED",),
            None,
            None
        )
    ]
)
def test_valid_transitions(
    current, event, states, command, target
):
    result = get_transition(current, event)

    assert result is not None
    assert result.states == states
    assert result.command == command
    assert result.target == target


# ==================================================
# TRANSICIONES INCOMPATIBLES
# ==================================================

@pytest.mark.parametrize(
    "current,event",
    [
        ("REQUESTED", "TRANSFER_RECEIVED"),
        ("RESERVING_SOURCE", "TRANSFER_SHIPPED"),
        ("RESERVING_SOURCE", "TRANSFER_RECEIVED"),
        ("SOURCE_RESERVED", "STOCK_RESERVED"),
        ("DESTINATION_PENDING", "TRANSFER_SHIPPED"),
        ("COMPENSATING", "TRANSFER_RECEIVED")
    ]
)
def test_invalid_transitions(current, event):

    assert get_transition(current, event) is None


# ==================================================
# ESTADOS TERMINALES
# ==================================================

@pytest.mark.parametrize(
    "status",
    ["COMPLETED", "FAILED", "CANCELLED"]
)
@pytest.mark.parametrize(
    "event",
    [
        "STOCK_RESERVED",
        "STOCK_RESERVATION_FAILED",
        "TRANSFER_SHIPPED",
        "TRANSFER_RECEIVED",
        "TRANSFER_RECEIVE_FAILED",
        "STOCK_RETURNED",
        "RESERVATION_RELEASED"
    ]
)
def test_terminal_states_are_immutable(status, event):

    assert get_transition(status, event) is None


def test_terminal_states_definition():

    assert TERMINAL_STATES == {
        TransferStatus.COMPLETED,
        TransferStatus.FAILED,
        TransferStatus.CANCELLED
    }


def test_unknown_event():

    assert get_transition(
        "RESERVING_SOURCE",
        "UNKNOWN_EVENT"
    ) is None
