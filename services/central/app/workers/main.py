import logging
import signal
import threading

from sqlalchemy import text

from common.logging import configure_logging

from app import config
from app.domain.database import SessionLocal


# Configuracion de logs del worker
configure_logging(
    "central-worker",
    None,
    config.LOG_LEVEL
)

logger = logging.getLogger("central-worker")

# Evento que controla la finalizacion del proceso
stop_event = threading.Event()


def handle_shutdown(signum, frame):
    """Permite detener el worker correctamente."""
    logger.info(
        "central_worker_shutdown_requested",
        extra={"signal": signum}
    )
    stop_event.set()


def main():
    """Inicializa el worker de la plataforma central."""

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("central_worker_starting")

    # Verificar la conexion con PostgreSQL
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))

    logger.info("central_worker_database_ready")

    # E-03: proceso base.
    # E-04: aqui se integrara la proyeccion CQRS.
    # E-06: se incorporara el orquestador Saga.
    logger.info("central_worker_waiting_for_implementation")

    # Mantener el proceso activo hasta recibir SIGTERM/SIGINT
    stop_event.wait()

    logger.info("central_worker_stopped")


if __name__ == "__main__":
    main()
