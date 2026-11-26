"""Métricas HTTP compartidas (S-07): plantilla de ruta, contador e histograma."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from common.metrics import observe_request

import time


def make_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def metrics_middleware(request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        observe_request(request, response.status_code, time.perf_counter() - start)
        return response

    @app.get("/items/{item_id}")
    def item(item_id: int):
        return {"id": item_id}

    return app


def sample(name: str, labels: dict) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_requests_are_counted_by_route_template_not_by_url():
    client = TestClient(make_app())
    labels = {"method": "GET", "route": "/items/{item_id}", "status": "200"}
    before = sample("http_requests_total", labels)

    client.get("/items/1")
    client.get("/items/2")

    assert sample("http_requests_total", labels) == before + 2


def test_unknown_routes_share_one_series():
    client = TestClient(make_app())
    labels = {"method": "GET", "route": "unmatched", "status": "404"}
    before = sample("http_requests_total", labels)

    client.get("/nada-1")
    client.get("/nada-2")

    assert sample("http_requests_total", labels) == before + 2


def test_duration_histogram_counts_each_request():
    client = TestClient(make_app())
    labels = {"method": "GET", "route": "/items/{item_id}"}
    before = sample("http_request_duration_seconds_count", labels)

    client.get("/items/9")

    assert sample("http_request_duration_seconds_count", labels) == before + 1
