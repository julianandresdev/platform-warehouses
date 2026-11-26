from fastapi import FastAPI
from fastapi.testclient import TestClient

from common.instance import InstanceHeaderMiddleware, instance_name


def _client(**kwargs):
    app = FastAPI()
    app.add_middleware(InstanceHeaderMiddleware, **kwargs)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    return TestClient(app)


def test_responde_x_instance_con_el_hostname(monkeypatch):
    monkeypatch.setenv("HOSTNAME", "wh002-api-2")
    r = _client().get("/ok")
    assert r.headers["X-Instance"] == "wh002-api-2"


def test_sin_hostname_usa_el_del_sistema(monkeypatch):
    monkeypatch.delenv("HOSTNAME", raising=False)
    assert instance_name()
    assert _client().get("/ok").headers["X-Instance"] == instance_name()


def test_tambien_en_respuestas_de_error(monkeypatch):
    monkeypatch.setenv("HOSTNAME", "r1")
    r = _client().get("/no-existe")
    assert r.status_code == 404
    assert r.headers["X-Instance"] == "r1"
