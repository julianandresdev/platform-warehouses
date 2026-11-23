
import argparse
import csv
import hashlib
import io
import json
import logging
import os

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import boto3
from sqlalchemy import create_engine, text


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("warehouse-exporter")


BODEGAS = {
    "WH-001": "WH001_DATABASE_URL",
    "WH-002": "WH002_DATABASE_URL",
    "WH-003": "WH003_DATABASE_URL",
}


COLUMNAS = [
    "id",
    "product_id",
    "warehouse_id",
    "type",
    "quantity",
    "reference",
    "created_at",
]


CONSULTA = text("""
    SELECT
        id,
        product_id,
        warehouse_id,
        type::text AS type,
        quantity,
        reference,
        created_at
    FROM inventory_movements
    WHERE warehouse_id = :warehouse_id
      AND created_at >= :inicio
      AND created_at < :fin
    ORDER BY created_at, id
""")


def consultar_movimientos(warehouse_id, variable, fecha):
    engine = create_engine(
        os.environ[variable],
        pool_pre_ping=True,
    )

    zona_colombia = ZoneInfo("America/Bogota")
    zona_utc = ZoneInfo("UTC")

    # Inicio del día solicitado en Colombia
    inicio_local = datetime.combine(
        fecha,
        time.min,
        tzinfo=zona_colombia,
    )

    # Inicio del día siguiente en Colombia
    fin_local = datetime.combine(
        fecha + timedelta(days=1),
        time.min,
        tzinfo=zona_colombia,
    )

    # PostgreSQL almacena TIMESTAMP sin zona horaria
    # y los valores representan horas UTC.
    inicio = inicio_local.astimezone(zona_utc).replace(
        tzinfo=None
    )

    fin = fin_local.astimezone(zona_utc).replace(
        tzinfo=None
    )

    try:
        with engine.connect() as conexion:
            resultado = conexion.execute(
                CONSULTA,
                {
                    "warehouse_id": warehouse_id,
                    "inicio": inicio,
                    "fin": fin,
                },
            )

            movimientos = [
                dict(fila)
                for fila in resultado.mappings()
            ]

        logger.info(
            "%s: %d movimientos",
            warehouse_id,
            len(movimientos),
        )

        return movimientos

    finally:
        engine.dispose()


def generar_csv(movimientos):
    salida = io.StringIO(newline="")

    escritor = csv.DictWriter(
        salida,
        fieldnames=COLUMNAS,
        lineterminator="\n",
    )

    escritor.writeheader()

    for movimiento in movimientos:
        fila = dict(movimiento)

        fila["created_at"] = fila["created_at"].isoformat(
            sep=" "
        )

        escritor.writerow(fila)

    return salida.getvalue().encode("utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Exportar movimientos diarios de bodegas a S3"
    )

    parser.add_argument(
        "--date",
        required=True,
        type=date.fromisoformat,
        help="Fecha del reporte en Colombia (YYYY-MM-DD)",
    )

    argumentos = parser.parse_args()
    fecha = argumentos.date

    bucket = os.environ["REPORT_BUCKET"]

    cliente_s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
    )

    archivos = {}

    # Primero consultar las tres bodegas.
    # Si alguna conexión falla, no publicar archivos parciales.
    for warehouse_id, variable in BODEGAS.items():
        movimientos = consultar_movimientos(
            warehouse_id,
            variable,
            fecha,
        )

        archivos[warehouse_id] = generar_csv(
            movimientos
        )

    prefijo = (
        f"inputs/movements/daily/"
        f"{fecha.isoformat()}/"
    )

    # Publicar los CSV por fecha.
    for warehouse_id, contenido in archivos.items():
        clave = f"{prefijo}{warehouse_id}.csv"

        cliente_s3.put_object(
            Bucket=bucket,
            Key=clave,
            Body=contenido,
            ContentType="text/csv",
        )

        logger.info(
            "Exportado s3://%s/%s",
            bucket,
            clave,
        )

    # Crear el manifiesto de exportación.
    manifiesto = {
        "report_date": fecha.isoformat(),
        "status": "COMPLETE",
        "exported_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_timezone": "UTC",
        "report_timezone": "America/Bogota",
        "warehouses": {},
    }

    for warehouse_id, contenido in archivos.items():
        clave = f"{prefijo}{warehouse_id}.csv"

        manifiesto["warehouses"][warehouse_id] = {
            "key": clave,
            "sha256": hashlib.sha256(
                contenido
            ).hexdigest(),
        }

    # Publicar el manifiesto al final,
    # una vez subidos los tres CSV.
    clave_manifiesto = f"{prefijo}manifest.json"

    cliente_s3.put_object(
        Bucket=bucket,
        Key=clave_manifiesto,
        Body=json.dumps(
            manifiesto,
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(
        "Manifiesto guardado: s3://%s/%s",
        bucket,
        clave_manifiesto,
    )

    logger.info(
        "Exportacion completada para %s",
        fecha.isoformat(),
    )


if __name__ == "__main__":
    main()
