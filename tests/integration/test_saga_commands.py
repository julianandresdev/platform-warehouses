"""Pruebas de integración del worker de comandos de la Saga (J-07).

Necesitan una base de bodega con schema.sql y las migraciones aplicadas
(DATABASE_URL). Cada prueba crea su propio producto con un SKU único y borra
todo lo que generó al terminar, así que puede correr sobre una base con seed.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

DATABASE_URL = os.getenv("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="define DATABASE_URL para probar los comandos de la Saga"
)

SOURCE = "WH-001"
DESTINATION = "WH-002"


@pytest.fixture
def db():
    from sqlalchemy import text

    from database import SessionLocal

    created: dict[str, list] = {"skus": [], "transfers": [], "messages": []}

    def make_product(stock: dict[str, int]) -> str:
        sku = f"SAGA-{uuid.uuid4().hex[:12]}"
        with SessionLocal() as session, session.begin():
            product_id = session.execute(
                text(
                    "INSERT INTO products (sku, name, unit) "
                    "VALUES (:sku, 'Prueba Saga', 'unidad') RETURNING id"
                ),
                {"sku": sku},
            ).scalar_one()
            for warehouse_id, quantity in stock.items():
                session.execute(
                    text(
                        "INSERT INTO inventory (product_id, warehouse_id, quantity) "
                        "VALUES (:product_id, :warehouse_id, :quantity)"
                    ),
                    {
                        "product_id": product_id,
                        "warehouse_id": warehouse_id,
                        "quantity": quantity,
                    },
                )
        created["skus"].append(sku)
        return sku

    class Helper:
        session_factory = SessionLocal
        product = staticmethod(make_product)

        @staticmethod
        def command(
            command_type: str,
            sku: str,
            quantity: int,
            *,
            warehouse_id: str = SOURCE,
            transfer_id: str | None = None,
            deadline: datetime | None = None,
        ) -> dict:
            transfer_id = transfer_id or str(uuid.uuid4())
            payload = {
                "transfer_id": transfer_id,
                "warehouse_id": warehouse_id,
                "sku": sku,
                "quantity": quantity,
            }
            if command_type == "RESERVE_STOCK":
                deadline = deadline or datetime.now(timezone.utc) + timedelta(seconds=30)
                payload["deadline"] = deadline.isoformat().replace("+00:00", "Z")
            event_id = str(uuid.uuid4())
            created["transfers"].append(transfer_id)
            created["messages"].append(event_id)
            return {
                "event_id": event_id,
                "event_type": command_type,
                "event_version": 1,
                "occurred_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "correlation_id": f"COR-TEST-{uuid.uuid4().hex[:8]}",
                "source": "central",
                "payload": payload,
            }

        @staticmethod
        def inventory(sku: str, warehouse_id: str = SOURCE) -> tuple[int, int] | None:
            with SessionLocal() as session:
                row = session.execute(
                    text(
                        "SELECT i.quantity, i.reserved_quantity FROM inventory i "
                        "JOIN products p ON p.id = i.product_id "
                        "WHERE p.sku = :sku AND i.warehouse_id = :warehouse_id"
                    ),
                    {"sku": sku, "warehouse_id": warehouse_id},
                ).first()
            return None if row is None else (row.quantity, row.reserved_quantity)

        @staticmethod
        def movements(transfer_id: str, warehouse_id: str = SOURCE) -> list[tuple[str, int]]:
            with SessionLocal() as session:
                rows = session.execute(
                    text(
                        "SELECT type::text AS type, quantity FROM inventory_movements "
                        "WHERE reference = :reference AND warehouse_id = :warehouse_id "
                        "ORDER BY id"
                    ),
                    {"reference": f"transfer:{transfer_id}", "warehouse_id": warehouse_id},
                ).all()
            return [(row.type, row.quantity) for row in rows]

        @staticmethod
        def outbox(transfer_id: str, sku: str) -> list[dict]:
            """Eventos de respuesta del transfer + INVENTORY_UPDATED del SKU."""

            with SessionLocal() as session:
                rows = session.execute(
                    text(
                        "SELECT routing_key, payload FROM outbox "
                        "WHERE payload->'payload'->>'transfer_id' = :transfer_id "
                        "   OR (payload->>'event_type' = 'INVENTORY_UPDATED' "
                        "       AND payload->'payload'->>'sku' = :sku) "
                        "ORDER BY id"
                    ),
                    {"transfer_id": transfer_id, "sku": sku},
                ).all()
            return [{"routing_key": row.routing_key, **row.payload} for row in rows]

        @staticmethod
        def processed(event_id: str) -> int:
            with SessionLocal() as session:
                return session.execute(
                    text(
                        "SELECT count(*) FROM processed_messages "
                        "WHERE message_id = CAST(:event_id AS UUID)"
                    ),
                    {"event_id": event_id},
                ).scalar_one()

    yield Helper

    with SessionLocal() as session, session.begin():
        for sku in created["skus"]:
            session.execute(
                text(
                    "DELETE FROM outbox WHERE payload->'payload'->>'sku' = :sku"
                ),
                {"sku": sku},
            )
            for table in ("inventory_movements", "inventory"):
                session.execute(
                    text(
                        f"DELETE FROM {table} WHERE product_id = "
                        "(SELECT id FROM products WHERE sku = :sku)"
                    ),
                    {"sku": sku},
                )
            session.execute(text("DELETE FROM products WHERE sku = :sku"), {"sku": sku})
        for event_id in created["messages"]:
            session.execute(
                text(
                    "DELETE FROM processed_messages "
                    "WHERE message_id = CAST(:event_id AS UUID)"
                ),
                {"event_id": event_id},
            )


def run(db, message, warehouse_id=SOURCE, **kwargs):
    from workers.commands import handle_command

    kwargs.setdefault("chaos", "")
    return handle_command(
        message, session_factory=db.session_factory, warehouse_id=warehouse_id, **kwargs
    )


def event_types(events: list[dict]) -> list[str]:
    return [event["event_type"] for event in events]


# -------------------------
# RESERVE_STOCK
# -------------------------

def test_reserve_stock_reserves_and_emits_events(db):
    sku = db.product({SOURCE: 100})
    message = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = message["payload"]["transfer_id"]

    outcome = run(db, message)

    assert outcome.status == "processed"
    assert outcome.response_type == "STOCK_RESERVED"
    assert db.inventory(sku) == (100, 30)
    assert db.movements(transfer_id) == [("RESERVATION", 30)]
    events = db.outbox(transfer_id, sku)
    assert event_types(events) == ["STOCK_RESERVED", "INVENTORY_UPDATED"]
    reserved, updated = events
    assert reserved["routing_key"] == f"warehouse.{SOURCE}.transfer.stock_reserved"
    assert reserved["correlation_id"] == message["correlation_id"]
    assert reserved["payload"] == {
        "transfer_id": transfer_id,
        "warehouse_id": SOURCE,
        "sku": sku,
        "quantity": 30,
    }
    assert updated["routing_key"] == f"warehouse.{SOURCE}.inventory.updated"
    assert updated["payload"]["reserved_quantity"] == 30
    assert updated["payload"]["movement_type"] == "RESERVATION"
    assert db.processed(message["event_id"]) == 1


def test_reserve_stock_duplicate_is_acked_without_repeating(db):
    sku = db.product({SOURCE: 100})
    message = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = message["payload"]["transfer_id"]

    first = run(db, message)
    second = run(db, message)

    assert first.status == "processed"
    assert second.status == "duplicate"
    assert db.inventory(sku) == (100, 30)
    assert db.movements(transfer_id) == [("RESERVATION", 30)]
    assert event_types(db.outbox(transfer_id, sku)) == ["STOCK_RESERVED", "INVENTORY_UPDATED"]
    assert db.processed(message["event_id"]) == 1


def test_reserve_stock_resent_with_new_event_id_does_not_reserve_twice(db):
    sku = db.product({SOURCE: 100})
    first = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = first["payload"]["transfer_id"]
    resent = db.command("RESERVE_STOCK", sku, 30, transfer_id=transfer_id)

    run(db, first)
    outcome = run(db, resent)

    assert outcome.status == "processed"
    assert outcome.response_type == "STOCK_RESERVED"
    assert db.inventory(sku) == (100, 30)
    assert event_types(db.outbox(transfer_id, sku)) == [
        "STOCK_RESERVED",
        "INVENTORY_UPDATED",
        "STOCK_RESERVED",
    ]


def test_reserve_stock_fails_when_available_is_insufficient(db):
    sku = db.product({SOURCE: 100})
    run(db, db.command("RESERVE_STOCK", sku, 80))
    message = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = message["payload"]["transfer_id"]

    outcome = run(db, message)

    assert outcome.response_type == "STOCK_RESERVATION_FAILED"
    assert outcome.reason == "INSUFFICIENT_STOCK"
    assert db.inventory(sku) == (100, 80)
    assert db.movements(transfer_id) == []
    events = db.outbox(transfer_id, sku)
    failed = [event for event in events if event["event_type"] == "STOCK_RESERVATION_FAILED"]
    assert failed[0]["payload"]["reason"] == "INSUFFICIENT_STOCK"
    assert failed[0]["routing_key"] == f"warehouse.{SOURCE}.transfer.stock_reservation_failed"


def test_reserve_stock_respects_deadline(db):
    sku = db.product({SOURCE: 100})
    message = db.command(
        "RESERVE_STOCK",
        sku,
        30,
        deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    outcome = run(db, message)

    assert outcome.response_type == "STOCK_RESERVATION_FAILED"
    assert outcome.reason == "DEADLINE_EXCEEDED"
    assert db.inventory(sku) == (100, 0)


def test_reserve_stock_deadline_is_checked_after_waiting_for_the_lock(db):
    """La espera del FOR UPDATE cuenta contra el deadline.

    Otra transacción mantiene bloqueada la fila de inventario más tiempo que el
    margen del deadline. Si la hora se tomara antes de bloquear, el comando vería
    un deadline todavía vigente y reservaría con la fecha vencida.
    """

    import threading
    import time

    from sqlalchemy import text

    sku = db.product({SOURCE: 100})
    message = db.command(
        "RESERVE_STOCK",
        sku,
        30,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    transfer_id = message["payload"]["transfer_id"]
    holding = threading.Event()
    outcomes: list = []

    def competing_transaction() -> None:
        with db.session_factory() as session, session.begin():
            session.execute(
                text(
                    "SELECT 1 FROM inventory WHERE product_id = "
                    "(SELECT id FROM products WHERE sku = :sku) FOR UPDATE"
                ),
                {"sku": sku},
            )
            holding.set()
            time.sleep(2)

    holder = threading.Thread(target=competing_transaction)
    holder.start()
    assert holding.wait(timeout=10)
    worker = threading.Thread(target=lambda: outcomes.append(run(db, message)))
    worker.start()
    worker.join(timeout=15)
    holder.join(timeout=15)

    assert not worker.is_alive()
    (outcome,) = outcomes
    assert outcome.response_type == "STOCK_RESERVATION_FAILED"
    assert outcome.reason == "DEADLINE_EXCEEDED"
    assert db.inventory(sku) == (100, 0)
    assert db.movements(transfer_id) == []


def test_reserve_stock_unknown_sku_fails(db):
    message = db.command("RESERVE_STOCK", f"NOPE-{uuid.uuid4().hex[:8]}", 5)

    outcome = run(db, message)

    assert outcome.response_type == "STOCK_RESERVATION_FAILED"
    assert outcome.reason == "SKU_NOT_FOUND"


# -------------------------
# RELEASE_RESERVATION
# -------------------------

def test_release_reservation_frees_reserved_stock(db):
    sku = db.product({SOURCE: 100})
    reserve = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = reserve["payload"]["transfer_id"]
    run(db, reserve)
    release = db.command("RELEASE_RESERVATION", sku, 30, transfer_id=transfer_id)

    outcome = run(db, release)
    duplicate = run(db, release)

    assert outcome.response_type == "RESERVATION_RELEASED"
    assert duplicate.status == "duplicate"
    assert db.inventory(sku) == (100, 0)
    assert db.movements(transfer_id) == [("RESERVATION", 30), ("RESERVATION_RELEASE", 30)]


def test_release_without_reservation_confirms_without_changes(db):
    sku = db.product({SOURCE: 100})
    message = db.command("RELEASE_RESERVATION", sku, 30)

    outcome = run(db, message)

    assert outcome.response_type == "RESERVATION_RELEASED"
    assert outcome.events == ["RESERVATION_RELEASED"]
    assert db.inventory(sku) == (100, 0)


# -------------------------
# SHIP_TRANSFER
# -------------------------

def test_ship_transfer_consumes_reservation(db):
    sku = db.product({SOURCE: 100})
    reserve = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = reserve["payload"]["transfer_id"]
    run(db, reserve)
    ship = db.command("SHIP_TRANSFER", sku, 30, transfer_id=transfer_id)

    outcome = run(db, ship)
    duplicate = run(db, ship)

    assert outcome.response_type == "TRANSFER_SHIPPED"
    assert duplicate.status == "duplicate"
    assert db.inventory(sku) == (70, 0)
    assert db.movements(transfer_id) == [("RESERVATION", 30), ("TRANSFER_OUT", 30)]


def test_ship_without_reservation_emits_ship_failed(db):
    sku = db.product({SOURCE: 100})
    message = db.command("SHIP_TRANSFER", sku, 30)
    transfer_id = message["payload"]["transfer_id"]

    outcome = run(db, message)
    duplicate = run(db, message)

    assert outcome.status == "processed"
    assert outcome.response_type == "TRANSFER_SHIP_FAILED"
    assert outcome.reason == "NO_ACTIVE_RESERVATION"
    assert outcome.events == ["TRANSFER_SHIP_FAILED"]
    assert duplicate.status == "duplicate"
    assert db.inventory(sku) == (100, 0)
    assert db.movements(transfer_id) == []
    assert db.processed(message["event_id"]) == 1
    (failed,) = db.outbox(transfer_id, sku)
    assert failed["routing_key"] == f"warehouse.{SOURCE}.transfer.transfer_ship_failed"
    assert failed["correlation_id"] == message["correlation_id"]
    assert failed["payload"] == {
        "transfer_id": transfer_id,
        "warehouse_id": SOURCE,
        "sku": sku,
        "quantity": 30,
        "reason": "NO_ACTIVE_RESERVATION",
    }


def test_ship_after_release_emits_ship_failed(db):
    sku = db.product({SOURCE: 100})
    reserve = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = reserve["payload"]["transfer_id"]
    run(db, reserve)
    run(db, db.command("RELEASE_RESERVATION", sku, 30, transfer_id=transfer_id))

    outcome = run(db, db.command("SHIP_TRANSFER", sku, 30, transfer_id=transfer_id))

    assert outcome.response_type == "TRANSFER_SHIP_FAILED"
    assert outcome.reason == "NO_ACTIVE_RESERVATION"
    assert db.inventory(sku) == (100, 0)
    assert db.movements(transfer_id) == [("RESERVATION", 30), ("RESERVATION_RELEASE", 30)]


def test_ship_unknown_sku_emits_ship_failed(db):
    message = db.command("SHIP_TRANSFER", f"NOPE-{uuid.uuid4().hex[:8]}", 5)

    outcome = run(db, message)

    assert outcome.response_type == "TRANSFER_SHIP_FAILED"
    assert outcome.reason == "SKU_NOT_FOUND"


# -------------------------
# RECEIVE_TRANSFER
# -------------------------

def test_receive_transfer_adds_stock(db):
    sku = db.product({DESTINATION: 20})
    message = db.command("RECEIVE_TRANSFER", sku, 30, warehouse_id=DESTINATION)
    transfer_id = message["payload"]["transfer_id"]

    outcome = run(db, message, warehouse_id=DESTINATION)
    duplicate = run(db, message, warehouse_id=DESTINATION)

    assert outcome.response_type == "TRANSFER_RECEIVED"
    assert duplicate.status == "duplicate"
    assert db.inventory(sku, DESTINATION) == (50, 0)
    assert db.movements(transfer_id, DESTINATION) == [("TRANSFER_IN", 30)]


def test_receive_transfer_creates_inventory_row_if_missing(db):
    sku = db.product({})
    message = db.command("RECEIVE_TRANSFER", sku, 30, warehouse_id=DESTINATION)

    outcome = run(db, message, warehouse_id=DESTINATION)

    assert outcome.response_type == "TRANSFER_RECEIVED"
    assert db.inventory(sku, DESTINATION) == (30, 0)


def test_receive_transfer_unknown_sku_is_permanent_failure(db):
    message = db.command(
        "RECEIVE_TRANSFER", f"NOPE-{uuid.uuid4().hex[:8]}", 30, warehouse_id=DESTINATION
    )

    outcome = run(db, message, warehouse_id=DESTINATION)

    assert outcome.status == "processed"
    assert outcome.response_type == "TRANSFER_RECEIVE_FAILED"
    assert outcome.reason == "SKU_NOT_FOUND"
    assert outcome.events == ["TRANSFER_RECEIVE_FAILED"]


# -------------------------
# RETURN_STOCK
# -------------------------

def test_return_stock_compensates_shipment(db):
    sku = db.product({SOURCE: 100})
    reserve = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = reserve["payload"]["transfer_id"]
    run(db, reserve)
    run(db, db.command("SHIP_TRANSFER", sku, 30, transfer_id=transfer_id))
    message = db.command("RETURN_STOCK", sku, 30, transfer_id=transfer_id)

    outcome = run(db, message)
    duplicate = run(db, message)
    resent = run(db, db.command("RETURN_STOCK", sku, 30, transfer_id=transfer_id))

    assert outcome.response_type == "STOCK_RETURNED"
    assert duplicate.status == "duplicate"
    assert resent.response_type == "STOCK_RETURNED"
    assert db.inventory(sku) == (100, 0)
    assert db.movements(transfer_id) == [
        ("RESERVATION", 30),
        ("TRANSFER_OUT", 30),
        ("TRANSFER_RETURN", 30),
    ]


# -------------------------
# VALIDACIÓN Y CAOS
# -------------------------

def test_command_for_other_warehouse_is_ignored(db):
    sku = db.product({SOURCE: 100})
    message = db.command("RESERVE_STOCK", sku, 30, warehouse_id=DESTINATION)

    outcome = run(db, message, warehouse_id=SOURCE)

    assert outcome.status == "invalid"
    assert db.inventory(sku) == (100, 0)
    assert db.processed(message["event_id"]) == 0


def test_chaos_before_commit_leaves_nothing(db):
    from workers.commands import ChaosError

    sku = db.product({SOURCE: 100})
    message = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = message["payload"]["transfer_id"]

    with pytest.raises(ChaosError):
        run(db, message, chaos="RESERVE_STOCK:before_commit")

    assert db.inventory(sku) == (100, 0)
    assert db.processed(message["event_id"]) == 0
    assert db.outbox(transfer_id, sku) == []

    # La reentrega sin caos aplica el comando una sola vez.
    assert run(db, message).status == "processed"
    assert db.inventory(sku) == (100, 30)


def test_chaos_after_commit_redelivery_is_duplicate(db):
    from workers.commands import ChaosError

    sku = db.product({SOURCE: 100})
    message = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = message["payload"]["transfer_id"]

    with pytest.raises(ChaosError):
        run(db, message, chaos="*:after_commit")

    assert db.inventory(sku) == (100, 30)
    assert db.processed(message["event_id"]) == 1

    # RabbitMQ reentrega porque no hubo ack: se detecta el duplicado.
    assert run(db, message, chaos="*:after_commit").status == "duplicate"
    assert db.inventory(sku) == (100, 30)
    assert event_types(db.outbox(transfer_id, sku)) == ["STOCK_RESERVED", "INVENTORY_UPDATED"]


# -------------------------
# CASO 100/20 -> 70/50
# -------------------------

def test_transfer_100_20_ends_70_50(db):
    sku = db.product({SOURCE: 100, DESTINATION: 20})
    reserve = db.command("RESERVE_STOCK", sku, 30)
    transfer_id = reserve["payload"]["transfer_id"]

    assert run(db, reserve).response_type == "STOCK_RESERVED"
    assert db.inventory(sku, SOURCE) == (100, 30)
    ship = db.command("SHIP_TRANSFER", sku, 30, transfer_id=transfer_id)
    assert run(db, ship).response_type == "TRANSFER_SHIPPED"
    receive = db.command(
        "RECEIVE_TRANSFER", sku, 30, warehouse_id=DESTINATION, transfer_id=transfer_id
    )
    assert run(db, receive, warehouse_id=DESTINATION).response_type == "TRANSFER_RECEIVED"

    assert db.inventory(sku, SOURCE) == (70, 0)
    assert db.inventory(sku, DESTINATION) == (50, 0)
    # Conservación: 100 + 20 = 70 + 50.
    assert sum(db.inventory(sku, wh)[0] for wh in (SOURCE, DESTINATION)) == 120
