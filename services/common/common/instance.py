"""Header X-Instance: identifica qué réplica respondió (S-04).

Detrás de nginx todas las réplicas de una bodega comparten la misma API; este header
(el HOSTNAME del contenedor) permite ver el reparto del balanceador y qué instancia
atendió cada petición.
"""

import os
import socket

HEADER_NAME = "X-Instance"
_HEADER_BYTES = HEADER_NAME.lower().encode()


def instance_name() -> str:
    return os.environ.get("HOSTNAME") or socket.gethostname()


class InstanceHeaderMiddleware:
    """Middleware ASGI puro: añade X-Instance a toda respuesta HTTP."""

    def __init__(self, app, name: str | None = None):
        self.app = app
        self._value = (name or instance_name()).encode("latin-1", "replace")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = [h for h in message.get("headers", []) if h[0].lower() != _HEADER_BYTES]
                headers.append((HEADER_NAME.encode(), self._value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)
