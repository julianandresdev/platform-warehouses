"""Correlation ID: se lee de X-Correlation-ID o se genera, y viaja en un ContextVar."""

import secrets
from contextvars import ContextVar
from datetime import datetime, timezone

HEADER_NAME = "X-Correlation-ID"
_HEADER_BYTES = HEADER_NAME.lower().encode()

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def generate_correlation_id() -> str:
    """Formato COR-YYYYMMDD-<8 hex>, p. ej. COR-20261118-3fa2b1c4."""
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"COR-{day}-{secrets.token_hex(4)}"


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(value: str | None):
    """Fija el ID y devuelve el token para restaurarlo con reset_correlation_id."""
    return _correlation_id.set(value)


def reset_correlation_id(token) -> None:
    _correlation_id.reset(token)


class CorrelationIdMiddleware:
    """Middleware ASGI puro (evita los problemas de contexto de BaseHTTPMiddleware).

    Lee X-Correlation-ID (o genera uno), lo deja en el ContextVar durante todo el
    request y lo devuelve en la respuesta.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        correlation_id = None
        for name, value in scope.get("headers", []):
            if name == _HEADER_BYTES:
                correlation_id = value.decode("latin-1").strip()
                break
        # Se acota el largo: el valor termina en logs y en headers.
        if not correlation_id or len(correlation_id) > 100:
            correlation_id = generate_correlation_id()

        token = set_correlation_id(correlation_id)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", [])
                    if k.lower() != _HEADER_BYTES
                ]
                headers.append((_HEADER_BYTES, correlation_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            reset_correlation_id(token)
