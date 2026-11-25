from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text


@pytest.fixture
def sku(f1_client):
    response = f1_client.post(
        "/products",
        json={
            "sku": "E02-CONCURRENT",
            "name": "Producto de concurrencia",
            "unit": "unidad"
        }
    )

    assert response.status_code == 201

    return response.json()["sku"]


def concurrent_movements(
    client, sku, movement_type, quantity, workers
):
    """Ejecuta varias solicitudes HTTP concurrentes."""

    barrier = Barrier(workers)

    def send_movement():
        # Todos los hilos esperan antes de enviar la solicitud.
        barrier.wait(timeout=10)

        response = client.post(
            "/inventory/movements",
            json={
                "sku": sku,
                "type": movement_type,
                "quantity": quantity
            }
        )

        return response.status_code

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(send_movement)
            for _ in range(workers)
        ]

        return [
            future.result(timeout=30)
            for future in futures
        ]


def test_concurrent_shipments(f1_client, sku, clean_db):
    # Preparar un stock inicial de 10 unidades.
    response = f1_client.post(
        "/inventory/movements",
        json={
            "sku": sku,
            "type": "RECEIPT",
            "quantity": 10
        }
    )

    assert response.status_code == 201

    # Dos salidas concurrentes de 6 unidades.
    results = concurrent_movements(
        f1_client, sku, "SHIPMENT", 6, 2
    )

    assert sorted(results) == [201, 409]

    # Verificar el stock final.
    inventory = f1_client.get(
        f"/inventory/{sku}"
    ).json()

    assert inventory["quantity"] == 4
    assert inventory["version"] == 2

    # Solo debe existir una entrada y una salida.
    history = f1_client.get(
        f"/inventory/{sku}/movements"
    ).json()

    assert len(history) == 2
    assert history[0]["type"] == "SHIPMENT"
    assert history[0]["quantity"] == 6

    # Verificar directamente en PostgreSQL.
    with clean_db.connect() as connection:
        row = connection.execute(text("""
            SELECT quantity, version
            FROM inventory
        """)).one()

        assert row.quantity == 4
        assert row.version == 2

        count = connection.execute(text("""
            SELECT COUNT(*)
            FROM outbox
        """)).scalar_one()

        assert count == 2

    print(f"\nHTTP: {sorted(results)}")
    print("Stock final: 4")
    print("Version: 2")


def test_concurrent_first_receipts(
    f1_client, sku, clean_db
):
    # Cuatro primeras entradas simultaneas de 5 unidades.
    results = concurrent_movements(
        f1_client, sku, "RECEIPT", 5, 4
    )

    assert sorted(results) == [201, 201, 201, 201]

    inventory = f1_client.get(
        f"/inventory/{sku}"
    ).json()

    assert inventory["quantity"] == 20
    assert inventory["version"] == 4

    with clean_db.connect() as connection:
        rows = connection.execute(text("""
            SELECT quantity, version
            FROM inventory
        """)).all()

        # No pueden existir filas duplicadas.
        assert len(rows) == 1
        assert rows[0].quantity == 20
        assert rows[0].version == 4

        movements = connection.execute(text("""
            SELECT COUNT(*)
            FROM inventory_movements
        """)).scalar_one()

        assert movements == 4

    print(f"\nHTTP: {sorted(results)}")
    print("Stock final: 20")
    print("Filas de inventario: 1")
    print("Version: 4")
