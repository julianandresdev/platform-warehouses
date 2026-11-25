import os

import pytest
from pydantic import ValidationError


@pytest.fixture
def schemas_module(monkeypatch):
    # Los modelos importan database.py, pero estas pruebas
    # no necesitan establecer una conexion con PostgreSQL.
    if not os.getenv("DATABASE_URL"):
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg2://admin:admin@127.0.0.1:5542/platform_test"
        )

    import schemas

    return schemas


def test_valid_product(schemas_module):
    product = schemas_module.ProductCreate(
        sku="TEST-001",
        name="Laptop",
        unit="unidad"
    )

    assert product.sku == "TEST-001"
    assert product.name == "Laptop"
    assert product.unit == "unidad"


@pytest.mark.parametrize("field,value", [
    ("sku", ""),
    ("name", ""),
    ("unit", ""),
    ("sku", "A" * 101),
    ("name", "A" * 201),
    ("unit", "A" * 51),
])
def test_invalid_product(schemas_module, field, value):
    data = {
        "sku": "TEST-001",
        "name": "Laptop",
        "unit": "unidad"
    }

    data[field] = value

    with pytest.raises(ValidationError):
        schemas_module.ProductCreate(**data)


@pytest.mark.parametrize("movement_type,quantity", [
    ("RECEIPT", 10),
    ("SHIPMENT", 6),
    ("ADJUSTMENT", 8),
    ("ADJUSTMENT", 0),
])
def test_valid_movement(
    schemas_module, movement_type, quantity
):
    movement = schemas_module.MovementCreate(
        sku="TEST-001",
        type=movement_type,
        quantity=quantity
    )

    assert movement.quantity == quantity
    assert movement.type.value == movement_type


@pytest.mark.parametrize("movement_type,quantity", [
    ("RECEIPT", 0),
    ("RECEIPT", -5),
    ("SHIPMENT", 0),
    ("SHIPMENT", -5),
    ("ADJUSTMENT", -1),
    ("INVALID", 10),
])
def test_invalid_movement(
    schemas_module, movement_type, quantity
):
    with pytest.raises(ValidationError):
        schemas_module.MovementCreate(
            sku="TEST-001",
            type=movement_type,
            quantity=quantity
        )
