"""POST /internal/reports de la central (S-08): validación y respuesta, con la base simulada."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("API_KEY", "central-test-key")

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

KEY = {"X-API-Key": os.environ["API_KEY"]}
BODY = {
    "object_key": "reports/daily/2026-11-25/summary.json",
    "status": "VALID",
    "size": 888,
    "checksum": "a" * 64,
    "metadata": {"record_count": 23},
}


class FakeResult:
    def __init__(self, inserted: bool) -> None:
        self.inserted = inserted

    def scalar_one(self):
        return self.inserted


class FakeDb:
    def __init__(self, inserted: bool = True) -> None:
        self.inserted = inserted
        self.calls: list[dict] = []
        self.committed = False

    def execute(self, statement, params=None):
        self.calls.append(params)
        return FakeResult(self.inserted)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


CENTRAL = Path(__file__).resolve().parents[2] / "services" / "central"


@pytest.fixture
def client_for():
    # La bodega tiene un módulo ``app.py`` y la central un paquete ``app/``: se aísla
    # el import de la central para no pisar el ``app`` que usan otras pruebas.
    saved = {name: mod for name, mod in sys.modules.items() if name == "app" or name.startswith("app.")}
    for name in saved:
        del sys.modules[name]
    sys.path.insert(0, str(CENTRAL))
    try:
        from app.api.main import app
        from app.domain.database import get_db

        def make(db: FakeDb) -> TestClient:
            app.dependency_overrides[get_db] = lambda: db
            return TestClient(app)

        yield make
        app.dependency_overrides.clear()
    finally:
        sys.path.remove(str(CENTRAL))
        for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
            del sys.modules[name]
        sys.modules.update(saved)


def test_new_report_is_created_with_201(client_for):
    db = FakeDb(inserted=True)

    response = client_for(db).post("/internal/reports", json=BODY, headers=KEY)

    assert response.status_code == 201
    assert response.json()["object_key"] == BODY["object_key"]
    assert db.committed
    assert db.calls[0]["checksum"] == "a" * 64
    assert '"record_count": 23' in db.calls[0]["metadata"]


def test_repeated_report_updates_the_row_with_200(client_for):
    response = client_for(FakeDb(inserted=False)).post("/internal/reports", json=BODY, headers=KEY)

    assert response.status_code == 200


def test_requires_the_api_key(client_for):
    assert client_for(FakeDb()).post("/internal/reports", json=BODY).status_code == 401
    bad = {"X-API-Key": "otra"}
    assert client_for(FakeDb()).post("/internal/reports", json=BODY, headers=bad).status_code == 401


@pytest.mark.parametrize(
    "change",
    [{"object_key": ""}, {"status": ""}, {"size": -1}, {"checksum": "a" * 65}],
)
def test_invalid_bodies_are_rejected(client_for, change):
    response = client_for(FakeDb()).post("/internal/reports", json={**BODY, **change}, headers=KEY)

    assert response.status_code == 422


def test_the_body_the_lambda_sends_is_accepted(client_for):
    # Es el cuerpo de handler.process_object (tabla reports): sin size ni checksum también vale.
    response = client_for(FakeDb()).post(
        "/internal/reports",
        json={"object_key": "reports/jobs/x.json", "status": "INVALID", "metadata": {"reason": "no es JSON"}},
        headers=KEY,
    )

    assert response.status_code == 201
