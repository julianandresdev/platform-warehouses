"""Logs JSON con los campos comunes del proyecto.

Campos: timestamp, service, warehouse_id, level, event, correlation_id + extras.
`event` es el mensaje del log; los extras se pasan con `extra={...}`.
"""

import json
import logging
import sys
from datetime import datetime, timezone

from common.correlation import get_correlation_id

# Atributos que trae todo LogRecord: lo que no esté aquí es un extra del usuario.
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, warehouse_id: str | None = None):
        super().__init__()
        self.service = service
        self.warehouse_id = warehouse_id

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "service": self.service,
            "warehouse_id": self.warehouse_id,
            "level": record.levelname,
            "event": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in data:
                data[key] = value
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_logging(service: str, warehouse_id: str | None = None, level: str = "INFO") -> None:
    """Deja el logging raíz en JSON por stdout. Es idempotente."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service, warehouse_id))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # uvicorn usa sus propios handlers: se redirigen al raíz (JSON). El access log
    # de uvicorn se apaga porque la API registra cada request con correlation_id.
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
