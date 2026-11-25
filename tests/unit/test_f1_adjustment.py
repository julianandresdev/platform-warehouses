import pytest

from inventory_rules import (
    adjustment_delta,
    InvalidAdjustmentError
)


@pytest.mark.parametrize("current,counted,reserved,expected", [
    (10, 15, 0, 5),
    (10, 6, 0, -4),
    (10, 0, 0, -10),
    (0, 10, 0, 10),
    (10, 5, 5, -5),
])
def test_adjustment_delta(
    current, counted, reserved, expected
):
    assert adjustment_delta(
        current,
        counted,
        reserved
    ) == expected


def test_adjustment_below_reserved():
    with pytest.raises(InvalidAdjustmentError):
        adjustment_delta(10, 3, 5)


def test_adjustment_without_difference():
    with pytest.raises(InvalidAdjustmentError):
        adjustment_delta(10, 10, 0)
