"""GET /inventory y GET /movements, los endpoints de lectura que usa el batch (J-08)."""

from datetime import datetime

import pytest
from sqlalchemy import text


@pytest.fixture
def seeded(clean_db):
    """Un producto con tres movimientos a horas conocidas (created_at es UTC sin zona)."""

    with clean_db.begin() as connection:
        connection.execute(
            text("INSERT INTO products (sku, name, unit) VALUES ('J08-001', 'Producto J-08', 'unidad')")
        )
        product_id = connection.execute(
            text("SELECT id FROM products WHERE sku = 'J08-001'")
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO inventory (product_id, warehouse_id, quantity) "
                "VALUES (:p, 'WH-001', 12), (:p, 'WH-002', 99)"
            ),
            {"p": product_id},
        )
        for created_at, kind, quantity, warehouse_id in [
            ("2026-11-24 00:00:00", "RECEIPT", 10, "WH-001"),
            ("2026-11-24 12:30:00", "SHIPMENT", 3, "WH-001"),
            ("2026-11-25 00:00:00", "RECEIPT", 5, "WH-001"),
            ("2026-11-24 13:00:00", "RECEIPT", 7, "WH-002"),
        ]:
            connection.execute(
                text(
                    "INSERT INTO inventory_movements "
                    "(product_id, warehouse_id, type, quantity, created_at) "
                    "VALUES (:p, :w, CAST(:t AS movement_type), :q, :c)"
                ),
                {"p": product_id, "w": warehouse_id, "t": kind, "q": quantity,
                 "c": datetime.fromisoformat(created_at)},
            )
    return product_id


def movements(client, start, end, **params):
    return client.get("/movements", params={"from": start, "to": end, **params})


def test_inventory_lists_only_this_warehouse(f1_client, seeded):
    response = f1_client.get("/inventory")

    assert response.status_code == 200
    rows = response.json()
    assert [(row["sku"], row["warehouse_id"], row["quantity"]) for row in rows] == [
        ("J08-001", "WH-001", 12)
    ]


def test_movements_filter_is_inclusive_start_and_exclusive_end(f1_client, seeded):
    response = movements(f1_client, "2026-11-24T00:00:00Z", "2026-11-25T00:00:00Z")

    assert response.status_code == 200
    assert [(row["type"], row["quantity"]) for row in response.json()] == [
        ("RECEIPT", 10),
        ("SHIPMENT", 3),
    ]


def test_movements_only_include_this_warehouse(f1_client, seeded):
    response = movements(f1_client, "2026-11-24T00:00:00Z", "2026-11-26T00:00:00Z")

    assert {row["warehouse_id"] for row in response.json()} == {"WH-001"}


def test_movements_convert_the_offset_to_utc(f1_client, seeded):
    # 2026-11-23T19:00-05:00 == 2026-11-24T00:00Z, así que es la misma ventana.
    response = movements(f1_client, "2026-11-23T19:00:00-05:00", "2026-11-24T19:00:00-05:00")

    assert response.status_code == 200
    assert [row["quantity"] for row in response.json()] == [10, 3]


def test_movements_without_offset_are_read_as_utc(f1_client, seeded):
    response = movements(f1_client, "2026-11-24T00:00:00", "2026-11-25T00:00:00")

    assert [row["quantity"] for row in response.json()] == [10, 3]


def test_movements_are_paginated_without_repeating_rows(f1_client, seeded):
    first = movements(f1_client, "2026-11-24T00:00:00Z", "2026-11-26T00:00:00Z", page=1, page_size=2)
    second = movements(f1_client, "2026-11-24T00:00:00Z", "2026-11-26T00:00:00Z", page=2, page_size=2)
    third = movements(f1_client, "2026-11-24T00:00:00Z", "2026-11-26T00:00:00Z", page=3, page_size=2)

    assert [row["quantity"] for row in first.json()] == [10, 3]
    assert [row["quantity"] for row in second.json()] == [5]
    assert third.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-11-25T00:00:00Z", "to": "2026-11-24T00:00:00Z"},
        {"from": "2026-11-24T00:00:00Z", "to": "2026-11-24T00:00:00Z"},
        {"from": "ayer", "to": "2026-11-24T00:00:00Z"},
        {"from": "2026-11-24T00:00:00Z"},
        {"from": "2026-11-24T00:00:00Z", "to": "2026-11-25T00:00:00Z", "page": 0},
        {"from": "2026-11-24T00:00:00Z", "to": "2026-11-25T00:00:00Z", "page_size": 501},
    ],
)
def test_movements_reject_invalid_parameters(f1_client, params):
    assert f1_client.get("/movements", params=params).status_code == 422


def test_read_endpoints_require_the_api_key(f1_client):
    for path in ("/inventory", "/movements?from=2026-11-24T00:00:00Z&to=2026-11-25T00:00:00Z"):
        response = f1_client.get(path, headers={"X-API-Key": "otra"})
        assert response.status_code == 401
