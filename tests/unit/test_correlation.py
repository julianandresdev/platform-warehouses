import json
import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from common.correlation import CorrelationIdMiddleware, get_correlation_id
from common.logging import JsonFormatter

PATRON = re.compile(r"^COR-\d{8}-[0-9a-f]{8}$")


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/id")
    def leer():
        return {"id": get_correlation_id()}

    return TestClient(app)


def test_respeta_el_header_y_lo_devuelve(client):
    r = client.get("/id", headers={"X-Correlation-ID": "COR-TEST"})
    assert r.headers["X-Correlation-ID"] == "COR-TEST"
    assert r.json() == {"id": "COR-TEST"}


def test_genera_uno_si_falta(client):
    r = client.get("/id")
    assert PATRON.match(r.headers["X-Correlation-ID"])
    assert r.json()["id"] == r.headers["X-Correlation-ID"]


def test_no_se_filtra_entre_requests(client):
    client.get("/id", headers={"X-Correlation-ID": "COR-A"})
    r = client.get("/id")
    assert r.json()["id"] != "COR-A"


def test_header_demasiado_largo_se_reemplaza(client):
    r = client.get("/id", headers={"X-Correlation-ID": "x" * 500})
    assert PATRON.match(r.headers["X-Correlation-ID"])


def test_los_logs_json_llevan_el_correlation_id(client):
    lineas = []

    class Captura(logging.Handler):
        def emit(self, record):
            lineas.append(self.format(record))

    handler = Captura()
    handler.setFormatter(JsonFormatter("warehouse-api", "WH-001"))
    log = logging.getLogger("test-correlation")
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/x")
    def x():
        log.info("hola", extra={"sku": "P-001"})
        return {}

    TestClient(app).get("/x", headers={"X-Correlation-ID": "COR-TEST"})
    log.removeHandler(handler)

    data = json.loads(lineas[0])
    assert data["correlation_id"] == "COR-TEST"
    assert data["event"] == "hola"
    assert data["service"] == "warehouse-api"
    assert data["warehouse_id"] == "WH-001"
    assert data["level"] == "INFO"
    assert data["sku"] == "P-001"
    assert data["timestamp"].endswith("Z")
