"""Métricas HTTP compartidas por las APIs (S-07, ADR-0016).

Las dos APIs (bodega y central) registran cada request en el middleware que ya
loguea y exponen ``/metrics`` con ``generate_latest()``. La etiqueta ``route`` es
la plantilla de la ruta (``/inventory/{sku}``) y no la URL real, para no crear una
serie por cada valor de un parámetro.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Requests HTTP atendidos",
    ["method", "route", "status"],
)

HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "Duración de los requests HTTP",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

UNMATCHED = "unmatched"


def route_template(request) -> str:
    """Plantilla de la ruta que atendió el request, o ``unmatched`` (404)."""

    route = request.scope.get("route")
    return getattr(route, "path", None) or UNMATCHED


def observe_request(request, status_code: int, seconds: float) -> None:
    route = route_template(request)
    HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
    HTTP_DURATION.labels(request.method, route).observe(seconds)
