"""Contexto compartido para propagar correlation IDs en cada proceso."""

from contextvars import ContextVar, Token


correlation_id_context: ContextVar[str | None] = ContextVar(
    "correlation_id", default=None
)


def get_correlation_id() -> str | None:
    """Devuelve el correlation ID activo en el contexto actual."""

    return correlation_id_context.get()


def set_correlation_id(correlation_id: str | None) -> Token[str | None]:
    """Establece el ID activo y devuelve el token para restaurar el contexto."""

    return correlation_id_context.set(correlation_id)
