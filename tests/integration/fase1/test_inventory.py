import pytest

from sqlalchemy import text


@pytest.fixture
def sku(f1_client):
    response = f1_client.post(
        "/products",
        json={
            "sku": "E02-INV-001",
            "name": "Producto de inventario",
            "unit": "unidad"
        }
    )

    assert response.status_code == 201

    return response.json()["sku"]


def movement(client, sku, movement_type, quantity):
    return client.post(
        "/inventory/movements",
        json={
            "sku": sku,
            "type": movement_type,
            "quantity": quantity
        }
    )


def test_receipt_and_shipment(f1_client, sku):
    # Entrada de 10 unidades
    response = movement(f1_client, sku, "RECEIPT", 10)
    assert response.status_code == 201

    inventory = f1_client.get(f"/inventory/{sku}").json()

    assert inventory["quantity"] == 10
    assert inventory["version"] == 1

    # Salida de 6 unidades
    response = movement(f1_client, sku, "SHIPMENT", 6)
    assert response.status_code == 201

    inventory = f1_client.get(f"/inventory/{sku}").json()

    assert inventory["quantity"] == 4
    assert inventory["available_quantity"] == 4
    assert inventory["version"] == 2
    assert inventory["warehouse_id"] == "WH-001"

    history = f1_client.get(
        f"/inventory/{sku}/movements"
    ).json()

    assert len(history) == 2
    assert history[0]["type"] == "SHIPMENT"
    assert history[1]["type"] == "RECEIPT"


def test_insufficient_stock(f1_client, sku, clean_db):
    assert movement(
        f1_client, sku, "RECEIPT", 10
    ).status_code == 201

    # Intentar retirar 15 unidades cuando solo existen 10
    response = movement(f1_client, sku, "SHIPMENT", 15)

    assert response.status_code == 409

    inventory = f1_client.get(f"/inventory/{sku}").json()

    assert inventory["quantity"] == 10
    assert inventory["version"] == 1

    history = f1_client.get(
        f"/inventory/{sku}/movements"
    ).json()

    assert len(history) == 1
    assert history[0]["type"] == "RECEIPT"

    # La transaccion fallida tampoco debe generar eventos.
    with clean_db.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM outbox")
        ).scalar_one()

        assert count == 1


def test_shipment_without_inventory(
    f1_client, sku, clean_db
):
    response = movement(f1_client, sku, "SHIPMENT", 1)

    assert response.status_code == 409

    # El rollback debe eliminar incluso la fila de
    # inventario que se creo para realizar el bloqueo.
    with clean_db.connect() as connection:
        for table in (
            "inventory",
            "inventory_movements",
            "outbox"
        ):
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()

            assert count == 0


def test_adjustment(f1_client, sku):
    assert movement(
        f1_client, sku, "RECEIPT", 10
    ).status_code == 201

    # Conteo fisico de 6: diferencia de -4
    response = movement(f1_client, sku, "ADJUSTMENT", 6)

    assert response.status_code == 201
    assert response.json()["quantity"] == -4

    # Conteo fisico de 15: diferencia de +9
    response = movement(f1_client, sku, "ADJUSTMENT", 15)

    assert response.status_code == 201
    assert response.json()["quantity"] == 9

    inventory = f1_client.get(f"/inventory/{sku}").json()

    assert inventory["quantity"] == 15
    assert inventory["version"] == 3

    # No se permite un ajuste sin diferencia.
    response = movement(f1_client, sku, "ADJUSTMENT", 15)

    assert response.status_code == 409

    inventory = f1_client.get(f"/inventory/{sku}").json()

    assert inventory["quantity"] == 15
    assert inventory["version"] == 3


def test_reserved_stock(f1_client, sku, clean_db):
    assert movement(
        f1_client, sku, "RECEIPT", 10
    ).status_code == 201

    # Simular 5 unidades previamente reservadas.
    with clean_db.begin() as connection:
        connection.execute(text("""
            UPDATE inventory
            SET reserved_quantity = 5
        """))

    # Hay 10 unidades totales, pero solo 5 disponibles.
    response = movement(f1_client, sku, "SHIPMENT", 6)

    assert response.status_code == 409

    # Tampoco se permite contar menos de lo reservado.
    response = movement(f1_client, sku, "ADJUSTMENT", 4)

    assert response.status_code == 409

    inventory = f1_client.get(f"/inventory/{sku}").json()

    assert inventory["quantity"] == 10
    assert inventory["reserved_quantity"] == 5
    assert inventory["available_quantity"] == 5
    assert inventory["version"] == 1

    history = f1_client.get(
        f"/inventory/{sku}/movements"
    ).json()

    assert len(history) == 1
