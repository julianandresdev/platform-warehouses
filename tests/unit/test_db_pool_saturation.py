"""Atasco del pool de conexiones (J-06, visto en J-09): get_db async y 503 por pool agotado."""

from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://u:p@localhost/db")

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.exc import TimeoutError as PoolTimeoutError  # noqa: E402

import database  # noqa: E402
from pool_errors import register_pool_error_handler  # noqa: E402


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def sessions(monkeypatch):
    created: list[FakeSession] = []

    def factory() -> FakeSession:
        created.append(FakeSession())
        return created[-1]

    monkeypatch.setattr(database, "SessionLocal", factory)
    return created


def test_get_db_is_async_so_its_cleanup_does_not_need_a_thread():
    # Una dependencia con yield síncrona limpia en el pool de hilos; si está saturado, la
    # conexión no se libera y la API queda atascada (ver el docstring de get_db).
    assert inspect.isasyncgenfunction(database.get_db)


def test_the_session_is_closed_after_a_normal_request(sessions):
    app = FastAPI()

    @app.get("/ok")
    def ok(db=Depends(database.get_db)):
        return {"closed_inside": db.closed}

    assert TestClient(app).get("/ok").json() == {"closed_inside": False}
    assert [s.closed for s in sessions] == [True]


def test_the_session_is_closed_even_when_the_endpoint_fails(sessions):
    app = FastAPI()

    @app.get("/boom")
    def boom(db=Depends(database.get_db)):
        raise RuntimeError("falla")

    with pytest.raises(RuntimeError):
        TestClient(app).get("/boom")
    assert [s.closed for s in sessions] == [True]


def test_pool_timeout_comes_from_the_environment_and_defaults_to_five_seconds():
    assert database.DB_POOL_TIMEOUT == float(os.getenv("DB_POOL_TIMEOUT", "5"))
    assert database.engine.pool.timeout() == database.DB_POOL_TIMEOUT


def test_pool_exhaustion_answers_503_with_retry_after():
    app = FastAPI()
    register_pool_error_handler(app)

    @app.get("/saturado")
    def saturado():
        raise PoolTimeoutError("QueuePool limit of size 20 overflow 20 reached", None, None)

    response = TestClient(app).get("/saturado")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "2"
    assert "saturado" in response.json()["detail"].lower()


def test_other_errors_are_not_swallowed_by_the_pool_handler():
    app = FastAPI()
    register_pool_error_handler(app)

    @app.get("/otro")
    def otro():
        raise RuntimeError("otra cosa")

    with pytest.raises(RuntimeError):
        TestClient(app).get("/otro")
