"""Contra la API real (docker compose up). Se omiten si no responde.

    API_URL=http://localhost:8000 API_KEY=dev-api-key pytest tests/integration
"""

import os
import uuid

import httpx
import pytest

API_URL = os.getenv("API_URL", "http://localhost:8000")
HEADERS = {"X-API-Key": os.getenv("API_KEY", "dev-api-key")}


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=API_URL, headers=HEADERS, timeout=5) as client:
        try:
            if client.get("/health").status_code != 200:
                pytest.skip("la API no está sana")
        except httpx.HTTPError:
            pytest.skip("la API no está levantada")
        yield client


@pytest.fixture
def sku(api):
    """Producto nuevo con stock 10 para no depender de la semilla."""
    code = f"T-{uuid.uuid4().hex[:8]}"
    assert api.post("/products", json={"sku": code, "name": code, "unit": "u"}).status_code == 201
    mov = {"sku": code, "type": "RECEIPT", "quantity": 10}
    assert api.post("/inventory/movements", json=mov).status_code == 201
    return code


def test_miss_luego_hit(api, sku):
    primero = api.get(f"/inventory/{sku}")
    segundo = api.get(f"/inventory/{sku}")
    if primero.headers["X-Cache"] == "BYPASS":
        pytest.skip("caché desactivada o Redis caído")
    assert primero.headers["X-Cache"] == "MISS"
    assert segundo.headers["X-Cache"] == "HIT"
    assert primero.json() == segundo.json()


def test_salida_invalida_la_cache(api, sku):
    api.get(f"/inventory/{sku}")
    antes = api.get(f"/inventory/{sku}")
    if antes.headers["X-Cache"] == "BYPASS":
        pytest.skip("caché desactivada o Redis caído")
    assert antes.headers["X-Cache"] == "HIT" and antes.json()["quantity"] == 10

    mov = {"sku": sku, "type": "SHIPMENT", "quantity": 4}
    assert api.post("/inventory/movements", json=mov).status_code == 201

    despues = api.get(f"/inventory/{sku}")
    assert despues.headers["X-Cache"] == "MISS"
    assert despues.json()["quantity"] == 6


def test_inexistente_da_404_sin_cachear(api):
    r = api.get("/inventory/NO-EXISTE")
    assert r.status_code == 404
    assert api.get("/inventory/NO-EXISTE").headers.get("X-Cache") in ("MISS", "BYPASS")
