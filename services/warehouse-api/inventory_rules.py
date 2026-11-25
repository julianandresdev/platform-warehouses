"""Reglas de negocio del inventario independientes de PostgreSQL."""


class InvalidAdjustmentError(Exception):
    """El conteo fisico no se puede aplicar."""


def adjustment_delta(
    current_quantity: int,
    counted_quantity: int,
    reserved_quantity: int
) -> int:
    """Calcula la diferencia entre el conteo fisico y el stock."""

    if counted_quantity < reserved_quantity:
        raise InvalidAdjustmentError(
            "El conteo no puede ser menor que la cantidad reservada"
        )

    delta = counted_quantity - current_quantity

    if delta == 0:
        raise InvalidAdjustmentError(
            "El conteo coincide con el inventario: no hay diferencia que registrar"
        )

    return delta
