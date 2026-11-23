
import argparse
import csv
import io
import logging
import os
from datetime import date, datetime, time, timedelta

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

    inicio = datetime.combine(fecha, time.min)
    fin = inicio + timedelta(days=1)

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    argumentos = parser.parse_args()

    fecha = date.fromisoformat(argumentos.date)
    bucket = os.environ["REPORT_BUCKET"]

    cliente_s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
    )

    # Primero consultar las tres bodegas.
    # Si alguna conexión falla, no subir archivos parciales.
    archivos = {}

    for warehouse_id, variable in BODEGAS.items():
        movimientos = consultar_movimientos(
            warehouse_id,
            variable,
            fecha,
        )
        archivos[warehouse_id] = generar_csv(movimientos)

    # Guardar entradas separadas por fecha.
    for warehouse_id, contenido in archivos.items():
        clave = (
            f"inputs/movements/daily/"
            f"{fecha.isoformat()}/{warehouse_id}.csv"
        )

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

    logger.info(
        "Exportacion completada para %s",
        fecha,
    )


if __name__ == "__main__":
    main()
