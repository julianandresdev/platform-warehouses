from dataclasses import dataclass
from enum import StrEnum


class TransferStatus(StrEnum):
    REQUESTED = "REQUESTED"
    RESERVING_SOURCE = "RESERVING_SOURCE"
    SOURCE_RESERVED = "SOURCE_RESERVED"
    IN_TRANSIT = "IN_TRANSIT"
    DESTINATION_PENDING = "DESTINATION_PENDING"
    DESTINATION_RECEIVED = "DESTINATION_RECEIVED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Transition:
    states: tuple[TransferStatus, ...]
    command: str | None = None
    target: str | None = None


S = TransferStatus


# Transiciones permitidas por estado y evento.
TRANSITIONS = {
    # Reserva exitosa: ordenar el envio.
    (S.RESERVING_SOURCE, "STOCK_RESERVED"):
        Transition(
            (S.SOURCE_RESERVED,),
            "SHIP_TRANSFER",
            "source"
        ),

    # Reserva rechazada.
    (S.RESERVING_SOURCE, "STOCK_RESERVATION_FAILED"):
        Transition(
            (S.FAILED,)
        ),

    # Mercancia enviada: ordenar la recepcion.
    (S.SOURCE_RESERVED, "TRANSFER_SHIPPED"):
        Transition(
            (S.IN_TRANSIT, S.DESTINATION_PENDING),
            "RECEIVE_TRANSFER",
            "destination"
        ),

    # Recepcion exitosa.
    (S.DESTINATION_PENDING, "TRANSFER_RECEIVED"):
        Transition(
            (S.DESTINATION_RECEIVED, S.COMPLETED)
        ),

    # Recepcion rechazada: devolver stock al origen.
    (S.DESTINATION_PENDING, "TRANSFER_RECEIVE_FAILED"):
        Transition(
            (S.COMPENSATING,),
            "RETURN_STOCK",
            "source"
        ),

    # Confirmacion de devolucion.
    (S.COMPENSATING, "STOCK_RETURNED"):
        Transition(
            (S.CANCELLED,)
        ),

    # Confirmacion de liberacion de reserva.
    (S.COMPENSATING, "RESERVATION_RELEASED"):
        Transition(
            (S.CANCELLED,)
        ),
}


TERMINAL_STATES = frozenset({
    S.COMPLETED,
    S.FAILED,
    S.CANCELLED,
})


def get_transition(
    current_status: str,
    event_type: str
) -> Transition | None:
    """Determina la siguiente transicion de la Saga."""

    status = TransferStatus(current_status)

    return TRANSITIONS.get((status, event_type))
