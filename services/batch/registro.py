
import logging
import os

from sqlalchemy import create_engine, text

logger = logging.getLogger("warehouse-batch")


def obtener_engine():
    url = os.getenv("BATCH_DATABASE_URL")

    if not url:
        logger.warning(
            "BATCH_DATABASE_URL no configurada; "
            "registro PostgreSQL deshabilitado"
        )
        return None

    return create_engine(url, pool_pre_ping=True)


def iniciar_ejecucion(engine, fecha):
    if engine is None:
        return True

    with engine.begin() as conexion:
        resultado = conexion.execute(
            text("""
                INSERT INTO batch_runs (
                    report_date,
                    status,
                    started_at,
                    attempt_count
                )
                VALUES (
                    :fecha,
                    'RUNNING',
                    NOW(),
                    1
                )
                ON CONFLICT (report_date)
                DO UPDATE SET
                    status = 'RUNNING',
                    started_at = NOW(),
                    finished_at = NULL,
                    s3_key = NULL,
                    error_message = NULL,
                    attempt_count = batch_runs.attempt_count + 1
                WHERE batch_runs.status = 'FAILED'
                RETURNING report_date
            """),
            {"fecha": fecha},
        ).first()

    return resultado is not None


def finalizar_ejecucion(engine, fecha, clave):
    if engine is None:
        return

    with engine.begin() as conexion:
        conexion.execute(
            text("""
                UPDATE batch_runs
                SET status = 'SUCCEEDED',
                    finished_at = NOW(),
                    s3_key = :clave,
                    error_message = NULL
                WHERE report_date = :fecha
                  AND status = 'RUNNING'
            """),
            {"fecha": fecha, "clave": clave},
        )


def registrar_error(engine, fecha, error):
    if engine is None:
        return

    with engine.begin() as conexion:
        conexion.execute(
            text("""
                UPDATE batch_runs
                SET status = 'FAILED',
                    finished_at = NOW(),
                    error_message = :error
                WHERE report_date = :fecha
                  AND status = 'RUNNING'
            """),
            {"fecha": fecha, "error": str(error)[:2000]},
        )
