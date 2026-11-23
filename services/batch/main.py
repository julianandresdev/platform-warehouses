import hashlib
import argparse
import csv
import io
import json
import logging
import os
import registro_s3
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import boto3
from registro import (
    obtener_engine,
    iniciar_ejecucion,
    finalizar_ejecucion,
    registrar_error,
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("warehouse-batch")

BODEGAS = ("WH-001", "WH-002", "WH-003")

COLUMNAS = {
    "id",
    "product_id",
    "warehouse_id",
    "type",
    "quantity",
    "reference",
    "created_at",
}

TIPOS = {"RECEIPT", "SHIPMENT", "ADJUSTMENT"}


def obtener_fecha():
    parser = argparse.ArgumentParser(
        description="Reporte diario de movimientos de bodegas"
    )

    parser.add_argument(
        "--date",
        dest="fecha",
        type=date.fromisoformat,
        default=datetime.now(ZoneInfo("America/Bogota")).date(),
        help="Fecha del reporte en formato YYYY-MM-DD",
    )

    return parser.parse_args().fecha


def validar_manifiesto(cliente_s3, bucket, fecha):
    prefijo = (
        f"inputs/movements/daily/{fecha.isoformat()}/"
    )
    clave = f"{prefijo}manifest.json"

    respuesta = cliente_s3.get_object(
        Bucket=bucket,
        Key=clave,
    )
    manifiesto = json.loads(respuesta["Body"].read())

    if manifiesto.get("status") != "COMPLETE":
        raise ValueError("La exportación no está completa")

    if manifiesto.get("report_date") != fecha.isoformat():
        raise ValueError("La fecha del manifiesto no coincide")

    archivos = manifiesto.get("warehouses", {})

    if set(archivos) != set(BODEGAS):
        raise ValueError(
            "El manifiesto no contiene las tres bodegas"
        )

    for warehouse_id in BODEGAS:
        datos = archivos[warehouse_id]
        clave_esperada = f"{prefijo}{warehouse_id}.csv"

        if datos["key"] != clave_esperada:
            raise ValueError(
                f"Ruta incorrecta para {warehouse_id}"
            )

        respuesta_csv = cliente_s3.get_object(
            Bucket=bucket,
            Key=clave_esperada,
        )

        contenido = respuesta_csv["Body"].read()
        hash_real = hashlib.sha256(contenido).hexdigest()

        if hash_real != datos["sha256"]:
            raise ValueError(
                f"Integridad incorrecta en {warehouse_id}"
            )

    logger.info(
        "Manifiesto validado correctamente para %s",
        fecha.isoformat(),
    )


def leer_movimientos(cliente_s3, bucket, warehouse_id, fecha):
    clave = (
        f"inputs/movements/daily/"
        f"{fecha.isoformat()}/{warehouse_id}.csv"
    )

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

    movimientos = []
    ids_encontrados = set()

    for fila in lector:
        movimiento_id = int(fila["id"])
        product_id = int(fila["product_id"])
        cantidad = int(fila["quantity"])

        if movimiento_id <= 0 or product_id <= 0:
            raise ValueError(f"ID inválido en {clave}")

        if movimiento_id in ids_encontrados:
            raise ValueError(
                f"Movimiento duplicado: {movimiento_id} en {clave}"
            )

        ids_encontrados.add(movimiento_id)

        if fila["warehouse_id"] != warehouse_id:
            raise ValueError(
                f"Bodega incorrecta en {clave}: "
                f"{fila['warehouse_id']}"
            )

        tipo = fila["type"]

        if tipo not in TIPOS:
            raise ValueError(f"Movimiento desconocido: {tipo}")

        if cantidad == 0:
            raise ValueError(
                f"Cantidad inválida en movimiento {movimiento_id}"
            )

        if tipo in {"RECEIPT", "SHIPMENT"} and cantidad < 0:
            raise ValueError(
                f"Cantidad negativa no permitida para {tipo}"
            )

        fecha_movimiento = datetime.fromisoformat(
            fila["created_at"].strip()
        )

        # PostgreSQL utiliza TIMESTAMP sin zona horaria.
        # Se compara la fecha almacenada sin convertirla.
        if fecha_movimiento.date() != fecha:
            continue

        movimientos.append({
            "id": movimiento_id,
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "type": tipo,
            "quantity": cantidad,
            "reference": fila["reference"] or None,
            "created_at": fecha_movimiento.isoformat(),
        })

    movimientos.sort(
        key=lambda m: (m["created_at"], m["id"])
    )

    logger.info(
        "%s: %d movimientos correspondientes a %s",
        warehouse_id,
        len(movimientos),
        fecha.isoformat(),
    )

    return movimientos


def generar_reporte(cliente_s3, bucket, fecha):
    validar_manifiesto(cliente_s3, bucket, fecha)
    bodegas = {}
    total_entradas = 0
    total_salidas = 0
    total_ajustes = 0
    total_movimientos = 0

    for warehouse_id in BODEGAS:
        movimientos = leer_movimientos(
            cliente_s3,
            bucket,
            warehouse_id,
            fecha,
        )

        entradas = sum(
            m["quantity"]
            for m in movimientos
            if m["type"] == "RECEIPT"
        )

        salidas = sum(
            m["quantity"]
            for m in movimientos
            if m["type"] == "SHIPMENT"
        )

        ajustes = sum(
            m["quantity"]
            for m in movimientos
            if m["type"] == "ADJUSTMENT"
        )

        bodegas[warehouse_id] = {
            "total_movements": len(movimientos),
            "entries": entradas,
            "shipments": salidas,
            "adjustments": ajustes,
            "net_change": entradas - salidas + ajustes,
            "movements": movimientos,
        }

        total_movimientos += len(movimientos)
        total_entradas += entradas
        total_salidas += salidas
        total_ajustes += ajustes

    return {
        "report_type": "daily_inventory_movements",
        "report_date": fecha.isoformat(),
        "source": "s3_csv",
        "total_warehouses": len(BODEGAS),
        "total_movements": total_movimientos,
        "total_entries": total_entradas,
        "total_shipments": total_salidas,
        "total_adjustments": total_ajustes,
        "net_change": (
            total_entradas - total_salidas + total_ajustes
        ),
        "warehouses": bodegas,
    }



def subir_reporte(cliente_s3, bucket, reporte, fecha):
    clave = f"exports/daily-movements-{fecha.isoformat()}.json"

    contenido = json.dumps(
        reporte,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")

    # Evitar una nueva escritura si el reporte no cambio.
    try:
        respuesta = cliente_s3.get_object(
            Bucket=bucket,
            Key=clave,
        )
    except cliente_s3.exceptions.NoSuchKey:
        respuesta = None
    except Exception as error:
        codigo = (
            getattr(error, "response", {})
            .get("Error", {})
            .get("Code")
        )
        if codigo in {"404", "NoSuchKey", "NotFound"}:
            respuesta = None
        else:
            raise

    if respuesta is not None:
        anterior = respuesta["Body"].read()

        if anterior == contenido:
            logger.info(
                "Reporte sin cambios: s3://%s/%s",
                bucket,
                clave,
            )
            return clave

    cliente_s3.put_object(
        Bucket=bucket,
        Key=clave,
        Body=contenido,
        ContentType="application/json",
    )

    logger.info(
        "Reporte guardado en s3://%s/%s",
        bucket,
        clave,
    )

    return clave




def main():
    fecha = obtener_fecha()
    bucket = os.environ["REPORT_BUCKET"]

    cliente_s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
    )

    backend = os.getenv("BATCH_REGISTRY_BACKEND")

    if backend is None:
        backend = (
            "postgres"
            if os.getenv("BATCH_DATABASE_URL")
            else "s3"
        )

    if backend not in ("postgres", "s3"):
        raise ValueError(
            "BATCH_REGISTRY_BACKEND debe ser postgres o s3"
        )

    engine = None
    registro = None

    try:
        if backend == "postgres":
            engine = obtener_engine()

            if engine is None:
                raise RuntimeError(
                    "BATCH_DATABASE_URL es obligatoria "
                    "para el registro PostgreSQL"
                )

            autorizado = iniciar_ejecucion(engine, fecha)

        else:
            registro = registro_s3.iniciar_ejecucion(
                cliente_s3, bucket, fecha
            )
            autorizado = registro is not None

        if not autorizado:
            logger.info(
                "Ejecucion omitida para %s",
                fecha.isoformat(),
            )
            return

        logger.info(
            "Iniciando procesamiento diario para %s",
            fecha.isoformat(),
        )

        try:
            reporte = generar_reporte(
                cliente_s3, bucket, fecha
            )

            clave = subir_reporte(
                cliente_s3, bucket, reporte, fecha
            )

            if backend == "postgres":
                finalizar_ejecucion(engine, fecha, clave)
            else:
                registro_s3.finalizar_ejecucion(
                    cliente_s3, bucket, registro, clave
                )

            logger.info(
                "Proceso completado: fecha=%s, "
                "movimientos=%d, entradas=%d, "
                "salidas=%d, ajustes=%d, clave=%s",
                fecha.isoformat(),
                reporte["total_movements"],
                reporte["total_entries"],
                reporte["total_shipments"],
                reporte["total_adjustments"],
                clave,
            )

        except Exception as error:
            try:
                if backend == "postgres":
                    registrar_error(engine, fecha, error)
                else:
                    registro_s3.registrar_error(
                        cliente_s3, bucket, registro, error
                    )
            except Exception:
                logger.exception(
                    "No se pudo registrar el error del trabajo"
                )

            logger.exception("Fallo el procesamiento diario")
            raise

    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
