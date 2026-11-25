"""Worker de comandos de la Saga en la bodega (F6, J-07).

Consume ``wh-00X.commands`` y ejecuta los pasos que ordena el orquestador
central: RESERVE_STOCK, RELEASE_RESERVATION, SHIP_TRANSFER, RECEIVE_TRANSFER y
RETURN_STOCK. Cada comando se aplica en UNA transacción local que incluye:

1. la fila en ``processed_messages`` (primer paso: si choca, es duplicado),
2. el cambio de inventario y su movimiento,
3. las filas de outbox del evento de respuesta y de ``INVENTORY_UPDATED``.

El ack a RabbitMQ ocurre solo después del commit (``common.rabbit.consume``
confirma cuando el handler retorna). Si el proceso muere entre el commit y el
ack, RabbitMQ reentrega el mensaje y el paso 1 lo detecta como duplicado.

Además de la deduplicación por ``event_id``, cada paso es idempotente por
transferencia: los movimientos guardan ``reference = transfer:<id>``, así que un
comando repetido con otro ``event_id`` (p. ej. un reenvío de la central) vuelve a
emitir la respuesta sin mover stock dos veces.

``CHAOS_FAIL_STEP`` (solo pruebas) fuerza un fallo antes o después del commit;
ver :func:`chaos_point`.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

import cache
import config
import models
from common.events import EventEnvelope, new_event
from common.logging import configure_logging
from common.outbox import add_event
from common.rabbit import connect, consume, declare_topology

logger = logging.getLogger(__name__)
MAX_BACKOFF_SECONDS = 30

RESERVE_STOCK = "RESERVE_STOCK"
RELEASE_RESERVATION = "RELEASE_RESERVATION"
SHIP_TRANSFER = "SHIP_TRANSFER"
RECEIVE_TRANSFER = "RECEIVE_TRANSFER"
RETURN_STOCK = "RETURN_STOCK"

# Motivos de los eventos de fallo (campo `reason`).
REASON_DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
REASON_INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
REASON_SKU_NOT_FOUND = "SKU_NOT_FOUND"
REASON_NO_ACTIVE_RESERVATION = "NO_ACTIVE_RESERVATION"

CHAOS_STEPS = ("before_commit", "after_commit")

M = models.MovementType

# Reloj inyectable. Los pasos lo invocan en el momento exacto en que lo necesitan
# (p. ej. RESERVE_STOCK, después de tomar el lock del inventario) y no antes.
Clock = Callable[[], datetime]


class InvalidCommandError(ValueError):
    """El mensaje no es un comando válido: error permanente, no se reintenta."""


class ChaosError(RuntimeError):
    """Fallo inyectado con CHAOS_FAIL_STEP."""


@dataclass(frozen=True)
class Command:
    event_id: str
    event_type: str
    correlation_id: str
    transfer_id: str
    warehouse_id: str
    sku: str
    quantity: int
    deadline: datetime | None = None

    @property
    def reference(self) -> str:
        return f"transfer:{self.transfer_id}"


@dataclass
class StepResult:
    """Lo que produjo un comando dentro de la transacción."""

    response_type: str | None
    reason: str | None = None
    movement_type: models.MovementType | None = None
    inventory: models.Inventory | None = None
    note: str | None = None


@dataclass
class Outcome:
    """Resultado visible del handler (lo usan los logs y las pruebas)."""

    status: str  # processed | duplicate | invalid | rejected
    command_type: str | None = None
    response_type: str | None = None
    reason: str | None = None
    events: list[str] = field(default_factory=list)


# -------------------------
# PARSEO Y CAOS
# -------------------------

def _parse_deadline(value: Any) -> datetime:
    if not isinstance(value, str):
        raise InvalidCommandError("deadline debe ser una fecha ISO 8601")
    try:
        deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidCommandError("deadline no es una fecha ISO 8601 válida") from exc
    if deadline.tzinfo is None:
        raise InvalidCommandError("deadline debe incluir zona horaria (UTC)")
    return deadline.astimezone(timezone.utc)


def parse_command(message: dict[str, Any]) -> Command:
    """Valida el sobre y el payload según docs/events.md."""

    try:
        envelope = EventEnvelope.model_validate(message)
    except ValueError as exc:
        raise InvalidCommandError(f"Sobre inválido: {exc}") from exc

    if envelope.event_type not in HANDLERS:
        raise InvalidCommandError(f"Comando no soportado: {envelope.event_type}")
    if envelope.event_version != 1:
        raise InvalidCommandError(f"Versión no soportada: {envelope.event_version}")

    payload = envelope.payload
    try:
        transfer_id = str(uuid.UUID(str(payload["transfer_id"])))
        warehouse_id = payload["warehouse_id"]
        sku = payload["sku"]
        quantity = payload["quantity"]
    except KeyError as exc:
        raise InvalidCommandError(f"Falta el campo {exc.args[0]} en el payload") from exc
    except ValueError as exc:
        raise InvalidCommandError("transfer_id debe ser un UUID") from exc

    if not isinstance(warehouse_id, str) or not warehouse_id:
        raise InvalidCommandError("warehouse_id debe ser texto")
    if not isinstance(sku, str) or not sku:
        raise InvalidCommandError("sku debe ser texto")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise InvalidCommandError("quantity debe ser un entero mayor que 0")

    deadline = None
    if envelope.event_type == RESERVE_STOCK:
        if "deadline" not in payload:
            raise InvalidCommandError("RESERVE_STOCK requiere deadline")
        deadline = _parse_deadline(payload["deadline"])

    return Command(
        event_id=str(envelope.event_id),
        event_type=envelope.event_type,
        correlation_id=envelope.correlation_id,
        transfer_id=transfer_id,
        warehouse_id=warehouse_id,
        sku=sku,
        quantity=quantity,
        deadline=deadline,
    )


def chaos_point(command_type: str, step: str, setting: str | None = None) -> None:
    """Lanza ChaosError si CHAOS_FAIL_STEP pide fallar en este punto.

    Formato: lista separada por comas de ``<COMANDO>:<paso>`` o solo ``<paso>``
    (equivale a ``*:<paso>``), con paso ``before_commit`` o ``after_commit``.
    Ejemplos: ``SHIP_TRANSFER:after_commit``, ``*:before_commit``.

    - before_commit: la transacción se revierte; el mensaje se reencola y se
      reintenta (con el valor puesto, falla siempre: nada queda a medias).
    - after_commit: el efecto ya está confirmado pero no hay ack; la reentrega
      se detecta como duplicado y se confirma sin repetir el efecto.
    """

    if setting is None:
        setting = os.getenv("CHAOS_FAIL_STEP", "")
    for item in setting.split(","):
        item = item.strip()
        if not item:
            continue
        command, sep, when = item.partition(":")
        if not sep:
            command, when = "*", command
        if when not in CHAOS_STEPS:
            logger.warning("chaos_step_unknown", extra={"value": item})
            continue
        if when == step and command in ("*", command_type):
            logger.warning(
                "chaos_fail_injected", extra={"command": command_type, "step": step}
            )
            raise ChaosError(f"CHAOS_FAIL_STEP: {command_type} {step}")


# -------------------------
# PASOS DE LA SAGA
# -------------------------

def _product(session: Session, sku: str) -> models.Product | None:
    return session.query(models.Product).filter(models.Product.sku == sku).first()


def _lock_inventory(
    session: Session, product_id: int, warehouse_id: str, *, create: bool = False
) -> models.Inventory | None:
    """Bloquea (FOR UPDATE) la fila de inventario; con create la crea en 0."""

    if create:
        session.execute(
            pg_insert(models.Inventory)
            .values(
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=0,
                reserved_quantity=0,
                version=0,
            )
            .on_conflict_do_nothing(index_elements=["product_id", "warehouse_id"])
        )
    return (
        session.query(models.Inventory)
        .filter(
            models.Inventory.product_id == product_id,
            models.Inventory.warehouse_id == warehouse_id,
        )
        .with_for_update(of=models.Inventory)
        .populate_existing()
        .first()
    )


def _applied_steps(
    session: Session, product_id: int, warehouse_id: str, reference: str
) -> dict[models.MovementType, int]:
    """Movimientos ya registrados para esta transferencia en esta bodega.

    Se llama con la fila de inventario bloqueada, así que no hay carreras con
    otro comando de la misma transferencia.
    """

    rows = session.execute(
        text(
            """
            SELECT type, SUM(quantity) AS quantity
            FROM inventory_movements
            WHERE product_id = :product_id
              AND warehouse_id = :warehouse_id
              AND reference = :reference
            GROUP BY type
            """
        ),
        {"product_id": product_id, "warehouse_id": warehouse_id, "reference": reference},
    ).all()
    return {M(row.type): int(row.quantity) for row in rows}


def _active_reservation(steps: dict[models.MovementType, int]) -> int:
    """Unidades reservadas para la transferencia que siguen sin liberar ni despachar."""

    if M.RESERVATION not in steps:
        return 0
    if M.RESERVATION_RELEASE in steps or M.TRANSFER_OUT in steps:
        return 0
    return steps[M.RESERVATION]


def _record(
    session: Session,
    inventory: models.Inventory,
    command: Command,
    warehouse_id: str,
    movement_type: models.MovementType,
    quantity: int,
) -> None:
    inventory.version += 1
    session.add(
        models.InventoryMovement(
            product_id=inventory.product_id,
            warehouse_id=warehouse_id,
            type=movement_type,
            quantity=quantity,
            reference=command.reference,
        )
    )


def _reserve_stock(
    session: Session, command: Command, warehouse_id: str, now: Clock
) -> StepResult:
    failed = "STOCK_RESERVATION_FAILED"
    product = _product(session, command.sku)
    if product is None:
        return StepResult(failed, reason=REASON_SKU_NOT_FOUND)

    inventory = _lock_inventory(session, product.id, warehouse_id)
    if inventory is not None:
        steps = _applied_steps(session, product.id, warehouse_id, command.reference)
        if M.RESERVATION in steps:
            return StepResult("STOCK_RESERVED", note="reserva ya aplicada")

    # La hora se toma AQUÍ, con el lock del inventario ya adquirido: si el comando
    # esperó el FOR UPDATE detrás de otra transacción, esa espera cuenta contra el
    # deadline. Tomarla antes de bloquear dejaba reservar con la fecha vencida.
    if command.deadline is not None and now() >= command.deadline:
        return StepResult(failed, reason=REASON_DEADLINE_EXCEEDED)
    if inventory is None or inventory.available_quantity < command.quantity:
        return StepResult(failed, reason=REASON_INSUFFICIENT_STOCK)

    inventory.reserved_quantity += command.quantity
    _record(session, inventory, command, warehouse_id, M.RESERVATION, command.quantity)
    return StepResult("STOCK_RESERVED", movement_type=M.RESERVATION, inventory=inventory)


def _release_reservation(
    session: Session, command: Command, warehouse_id: str, now: Clock
) -> StepResult:
    released = "RESERVATION_RELEASED"
    product = _product(session, command.sku)
    if product is None:
        return StepResult(released, note="sku inexistente: nada que liberar")
    inventory = _lock_inventory(session, product.id, warehouse_id)
    if inventory is None:
        return StepResult(released, note="sin inventario: nada que liberar")

    steps = _applied_steps(session, product.id, warehouse_id, command.reference)
    reserved = _active_reservation(steps)
    if reserved == 0:
        return StepResult(released, note="sin reserva activa: nada que liberar")

    inventory.reserved_quantity -= reserved
    _record(session, inventory, command, warehouse_id, M.RESERVATION_RELEASE, reserved)
    return StepResult(released, movement_type=M.RESERVATION_RELEASE, inventory=inventory)


def _ship_transfer(
    session: Session, command: Command, warehouse_id: str, now: Clock
) -> StepResult:
    shipped = "TRANSFER_SHIPPED"
    failed = "TRANSFER_SHIP_FAILED"
    product = _product(session, command.sku)
    if product is None:
        return StepResult(failed, reason=REASON_SKU_NOT_FOUND)
    inventory = _lock_inventory(session, product.id, warehouse_id)
    if inventory is None:
        return StepResult(failed, reason=REASON_NO_ACTIVE_RESERVATION)

    steps = _applied_steps(session, product.id, warehouse_id, command.reference)
    if M.TRANSFER_OUT in steps:
        return StepResult(shipped, note="salida ya aplicada")
    reserved = _active_reservation(steps)
    if reserved == 0:
        # Nada que despachar (reserva inexistente, liberada o vencida): la central
        # recibe TRANSFER_SHIP_FAILED y compensa en vez de quedarse esperando.
        return StepResult(
            failed, reason=REASON_NO_ACTIVE_RESERVATION, note="sin reserva activa"
        )

    inventory.quantity -= reserved
    inventory.reserved_quantity -= reserved
    _record(session, inventory, command, warehouse_id, M.TRANSFER_OUT, reserved)
    return StepResult(shipped, movement_type=M.TRANSFER_OUT, inventory=inventory)


def _receive_transfer(
    session: Session, command: Command, warehouse_id: str, now: Clock
) -> StepResult:
    product = _product(session, command.sku)
    if product is None:
        # Falla permanente: el destino no maneja ese SKU.
        return StepResult("TRANSFER_RECEIVE_FAILED", reason=REASON_SKU_NOT_FOUND)

    inventory = _lock_inventory(session, product.id, warehouse_id, create=True)
    steps = _applied_steps(session, product.id, warehouse_id, command.reference)
    if M.TRANSFER_IN in steps:
        return StepResult("TRANSFER_RECEIVED", note="entrada ya aplicada")

    inventory.quantity += command.quantity
    _record(session, inventory, command, warehouse_id, M.TRANSFER_IN, command.quantity)
    return StepResult("TRANSFER_RECEIVED", movement_type=M.TRANSFER_IN, inventory=inventory)


def _return_stock(
    session: Session, command: Command, warehouse_id: str, now: Clock
) -> StepResult:
    returned = "STOCK_RETURNED"
    product = _product(session, command.sku)
    inventory = _lock_inventory(session, product.id, warehouse_id) if product else None
    if inventory is None:
        return StepResult(None, note="sku sin inventario en la bodega origen")

    steps = _applied_steps(session, product.id, warehouse_id, command.reference)
    if M.TRANSFER_RETURN in steps:
        return StepResult(returned, note="devolución ya aplicada")
    if M.TRANSFER_OUT in steps:
        quantity = steps[M.TRANSFER_OUT]
        inventory.quantity += quantity
        _record(session, inventory, command, warehouse_id, M.TRANSFER_RETURN, quantity)
        return StepResult(returned, movement_type=M.TRANSFER_RETURN, inventory=inventory)

    reserved = _active_reservation(steps)
    if reserved:
        # Nunca salió de la bodega: compensar es liberar la reserva.
        inventory.reserved_quantity -= reserved
        _record(session, inventory, command, warehouse_id, M.RESERVATION_RELEASE, reserved)
        return StepResult(
            returned, movement_type=M.RESERVATION_RELEASE, inventory=inventory
        )
    return StepResult(returned, note="nada que devolver")


StepHandler = Callable[[Session, Command, str, Clock], StepResult]

HANDLERS: dict[str, StepHandler] = {
    RESERVE_STOCK: _reserve_stock,
    RELEASE_RESERVATION: _release_reservation,
    SHIP_TRANSFER: _ship_transfer,
    RECEIVE_TRANSFER: _receive_transfer,
    RETURN_STOCK: _return_stock,
}


# -------------------------
# HANDLER DEL MENSAJE
# -------------------------

def consumer_name(warehouse_id: str) -> str:
    return f"{warehouse_id.lower()}.commands"


def _enqueue_events(
    session: Session, command: Command, result: StepResult, warehouse_id: str
) -> list[str]:
    source = f"warehouse-{warehouse_id}"
    events: list[str] = []

    if result.response_type is not None:
        payload: dict[str, Any] = {
            "transfer_id": command.transfer_id,
            "warehouse_id": warehouse_id,
            "sku": command.sku,
            "quantity": command.quantity,
        }
        if result.reason is not None:
            payload["reason"] = result.reason
        response = new_event(
            result.response_type, payload, source, correlation_id=command.correlation_id
        )
        add_event(
            session,
            response,
            exchange="warehouse.events",
            routing_key=f"warehouse.{warehouse_id}.transfer.{result.response_type.lower()}",
        )
        events.append(result.response_type)

    if result.inventory is not None and result.movement_type is not None:
        inventory = result.inventory
        updated = new_event(
            "INVENTORY_UPDATED",
            {
                "warehouse_id": warehouse_id,
                "sku": command.sku,
                "quantity": inventory.quantity,
                "reserved_quantity": inventory.reserved_quantity,
                "version": inventory.version,
                "movement_type": result.movement_type.value,
            },
            source,
            correlation_id=command.correlation_id,
        )
        add_event(
            session,
            updated,
            exchange="warehouse.events",
            routing_key=f"warehouse.{warehouse_id}.inventory.updated",
        )
        events.append("INVENTORY_UPDATED")
    return events


def handle_command(
    message: dict[str, Any],
    *,
    session_factory: sessionmaker[Session] | None = None,
    warehouse_id: str | None = None,
    now: Clock | None = None,
    chaos: str | None = None,
) -> Outcome:
    """Procesa un comando. Retorna normalmente => el consumidor hace ack.

    Los comandos inválidos se registran en el log y se confirman (no tiene
    sentido reintentarlos); D-05 los enviará a la DLQ. ChaosError y cualquier
    error de base de datos se propagan: el mensaje se reencola.
    """

    if session_factory is None:
        from database import SessionLocal

        session_factory = SessionLocal
    warehouse_id = warehouse_id or config.WAREHOUSE_ID
    now = now or (lambda: datetime.now(timezone.utc))

    try:
        command = parse_command(message)
    except InvalidCommandError as exc:
        logger.error(
            "command_invalid",
            extra={"error": str(exc), "event_id": message.get("event_id")},
        )
        return Outcome("invalid", command_type=message.get("event_type"))

    log_extra = {
        "command": command.event_type,
        "event_id": command.event_id,
        "transfer_id": command.transfer_id,
        "sku": command.sku,
        "quantity": command.quantity,
    }
    if command.warehouse_id != warehouse_id:
        logger.error(
            "command_wrong_warehouse",
            extra={**log_extra, "target_warehouse_id": command.warehouse_id},
        )
        return Outcome("invalid", command_type=command.event_type)

    with session_factory() as session:
        with session.begin():
            inserted = session.execute(
                text(
                    """
                    INSERT INTO processed_messages (message_id, consumer)
                    VALUES (CAST(:message_id AS UUID), :consumer)
                    ON CONFLICT DO NOTHING
                    RETURNING message_id
                    """
                ),
                {"message_id": command.event_id, "consumer": consumer_name(warehouse_id)},
            ).first()
            if inserted is None:
                logger.info("command_duplicate", extra=log_extra)
                return Outcome("duplicate", command_type=command.event_type)

            result = HANDLERS[command.event_type](session, command, warehouse_id, now)
            session.flush()
            events = _enqueue_events(session, command, result, warehouse_id)
            chaos_point(command.event_type, "before_commit", chaos)
        # COMMIT hecho.

    if result.inventory is not None:
        cache.invalidate_inventory(command.sku)
    chaos_point(command.event_type, "after_commit", chaos)

    status = "processed" if result.response_type is not None else "rejected"
    level = logging.INFO if status == "processed" else logging.ERROR
    logger.log(
        level,
        f"command_{status}",
        extra={
            **log_extra,
            "response": result.response_type,
            "reason": result.reason,
            "movement_type": result.movement_type.value if result.movement_type else None,
            "note": result.note,
        },
    )
    return Outcome(
        status,
        command_type=command.event_type,
        response_type=result.response_type,
        reason=result.reason,
        events=events,
    )


def run_worker() -> None:
    warehouse_id = config.WAREHOUSE_ID
    configure_logging("warehouse-commands", warehouse_id, config.LOG_LEVEL)
    queue = consumer_name(warehouse_id)
    failures = 0

    while True:
        connection = None
        try:
            connection = connect()
            declare_topology(connection.channel(), warehouse_ids=(warehouse_id,))
            logger.info("commands_worker_started", extra={"queue": queue})
            failures = 0
            consume(queue, lambda message: handle_command(message), connection=connection)
            return
        except KeyboardInterrupt:
            return
        except Exception:
            logger.exception("commands_worker_failed")
            delay = min(0.5 * (2**failures), MAX_BACKOFF_SECONDS)
            failures += 1
            logger.warning(
                "commands_worker_backoff",
                extra={"delay_seconds": delay, "consecutive_failures": failures},
            )
            time.sleep(delay)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    run_worker()
