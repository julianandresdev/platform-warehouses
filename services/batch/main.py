
import csv
import io
import json
import logging
import os
from datetime import datetime, timezone

import boto3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("warehouse-batch")

BODEGAS = ("WH-001", "WH-002", "WH-003")

COLUMNAS = {
    "sku",
    "name",
    "category",
    "unit",
    "warehouse_id",
    "quantity",
    "reserved_quantity",
    "available_quantity",
    "version",
}


def leer_inventario(cliente_s3, bucket, warehouse_id):
    clave = f"inputs/inventory/{warehouse_id}.csv"

    logger.info("Leyendo s3://%s/%s", bucket, clave)

    respuesta = cliente_s3.get_object(
        Bucket=bucket,
        Key=clave,
    )

    contenido = respuesta["Body"].read().decode("utf-8-sig")
    lector = csv.DictReader(io.StringIO(contenido))

    if not lector.fieldnames:
        raise ValueError(f"CSV sin encabezados: {clave}")

    faltantes = COLUMNAS - set(lector.fieldnames)

    if faltantes:
        raise ValueError(
            f"Columnas faltantes en {clave}: {sorted(faltantes)}"
        )

    productos = []
    sku_encontrados = set()

    for fila in lector:
        sku = fila["sku"]

        if not sku:
            raise ValueError(f"SKU vacío en {clave}")

        if sku in sku_encontrados:
            raise ValueError(f"SKU duplicado: {sku} en {clave}")

        sku_encontrados.add(sku)

        if fila["warehouse_id"] != warehouse_id:
            raise ValueError(
                f"Bodega incorrecta en {clave}: "
                f"{fila['warehouse_id']}"
            )

        cantidad = int(fila["quantity"])
        reservadas = int(fila["reserved_quantity"])
        disponibles = int(fila["available_quantity"])
        version = int(fila["version"])

        if cantidad < 0 or not 0 <= reservadas <= cantidad:
            raise ValueError(f"Inventario inválido: {sku}")

        if disponibles != cantidad - reservadas:
            raise ValueError(
                f"Cantidad disponible inconsistente: {sku}"
            )

        if version < 0:
            raise ValueError(f"Versión inválida: {sku}")

        productos.append({
            "sku": sku,
            "name": fila["name"],
            "category": fila["category"],
            "unit": fila["unit"],
            "warehouse_id": warehouse_id,
            "quantity": cantidad,
            "reserved_quantity": reservadas,
            "available_quantity": disponibles,
            "version": version,
        })

    logger.info(
        "%s: %d productos procesados",
        warehouse_id,
        len(productos),
    )

    return productos


def generar_reporte(cliente_s3, bucket):
    fecha = datetime.now(timezone.utc)
    inventarios = {}

    for warehouse_id in BODEGAS:
        inventarios[warehouse_id] = leer_inventario(
            cliente_s3,
            bucket,
            warehouse_id,
        )

    productos = [
        producto
        for registros in inventarios.values()
        for producto in registros
    ]

    reporte = {
        "generated_at": fecha.isoformat(),
        "report_type": "inventory_consolidated",
        "source": "s3_csv",
        "warehouses": inventarios,
        "total_products": len(productos),
        "total_units": sum(
            producto["quantity"] for producto in productos
        ),
        "total_reserved": sum(
            producto["reserved_quantity"]
            for producto in productos
        ),
        "total_available": sum(
            producto["available_quantity"]
            for producto in productos
        ),
    }

    return reporte, fecha


def subir_reporte(cliente_s3, bucket, reporte, fecha):
    nombre = fecha.strftime(
        "exports/inventory-report-%Y%m%dT%H%M%S%fZ.json"
    )

    contenido = json.dumps(
        reporte,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    cliente_s3.put_object(
        Bucket=bucket,
        Key=nombre,
        Body=contenido,
        ContentType="application/json",
    )

    logger.info(
        "Reporte guardado en s3://%s/%s",
        bucket,
        nombre,
    )


def main():
    bucket = os.environ["REPORT_BUCKET"]

    cliente_s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
    )

    logger.info("Iniciando procesamiento AWS Batch")

    reporte, fecha = generar_reporte(cliente_s3, bucket)

    subir_reporte(cliente_s3, bucket, reporte, fecha)

    logger.info(
        "Proceso completado: %d productos, "
        "%d unidades totales, %d reservadas, "
        "%d disponibles",
        reporte["total_products"],
        reporte["total_units"],
        reporte["total_reserved"],
        reporte["total_available"],
    )


if __name__ == "__main__":
    main()
