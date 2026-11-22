"""Clasificación de errores para los consumidores (F10).

- TransientError: puede funcionar si se reintenta (red, base caída, timeout).
- PermanentError: reintentar no sirve (payload inválido, versión no soportada);
  el mensaje va directo a la DLQ.
"""


class MessageError(Exception):
    """Base de los errores de procesamiento de mensajes."""


class TransientError(MessageError):
    """Fallo temporal: el mensaje se reintenta."""


class PermanentError(MessageError):
    """Fallo definitivo: el mensaje se envía a la DLQ sin reintentar."""
