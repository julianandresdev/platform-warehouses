
import json
import hashlib
import urllib.request
import uuid
from datetime import date
import logging
import os
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BODEGAS = {"WH-001", "WH-002", "WH-003"}


def validar_reporte(reporte):
    if not isinstance(reporte, dict):
        raise ValueError("El reporte debe ser un objeto JSON")

    if reporte.get("report_type") != "daily_inventory_movements":
        raise ValueError("Tipo de reporte no soportado")

    fecha = reporte.get("report_date")

    if not isinstance(fecha, str):
        raise ValueError("Falta la fecha del reporte")

    try:
        date.fromisoformat(fecha)
    except ValueError as error:
        raise ValueError("Fecha del reporte invalida") from error

    bodegas = reporte.get("warehouses")

    if not isinstance(bodegas, dict):
        raise ValueError("Falta el objeto warehouses")

    if set(bodegas) != BODEGAS:
        raise ValueError("El reporte debe incluir las tres bodegas")

    campos = (
        "total_movements",
        "total_entries",
        "total_shipments",
        "total_adjustments",
        "net_change",
    )

    for campo in campos:
        valor = reporte.get(campo)
        if type(valor) is not int:
            raise ValueError(f"Campo numerico invalido: {campo}")

    if reporte.get("total_warehouses") != 3:
        raise ValueError("Numero incorrecto de bodegas")

    total_movimientos = 0
    total_entradas = 0
    total_salidas = 0
    total_ajustes = 0

    for warehouse_id, datos in bodegas.items():
        if not isinstance(datos, dict):
            raise ValueError(f"Bodega invalida: {warehouse_id}")

        movimientos = datos.get("movements")

        if not isinstance(movimientos, list):
            raise ValueError(f"Movimientos invalidos en {warehouse_id}")

        for campo in (
            "total_movements",
            "entries",
            "shipments",
            "adjustments",
            "net_change",
        ):
            if type(datos.get(campo)) is not int:
                raise ValueError(
                    f"Campo invalido en {warehouse_id}: {campo}"
                )

        if len(movimientos) != datos["total_movements"]:
            raise ValueError(
                f"Cantidad de movimientos incorrecta en {warehouse_id}"
            )

        entradas = 0
        salidas = 0
        ajustes = 0

        for movimiento in movimientos:
            if not isinstance(movimiento, dict):
                raise ValueError("Movimiento no es un objeto")

            if movimiento.get("warehouse_id") != warehouse_id:
                raise ValueError("Bodega de movimiento incorrecta")

            tipo = movimiento.get("type")
            cantidad = movimiento.get("quantity")

            if type(cantidad) is not int or cantidad == 0:
                raise ValueError("Cantidad de movimiento invalida")

            if tipo == "RECEIPT" and cantidad > 0:
                entradas += cantidad
            elif tipo == "SHIPMENT" and cantidad > 0:
                salidas += cantidad
            elif tipo == "ADJUSTMENT":
                ajustes += cantidad
            else:
                raise ValueError("Tipo o cantidad de movimiento invalido")

        if (
            datos["entries"] != entradas
            or datos["shipments"] != salidas
            or datos["adjustments"] != ajustes
            or datos["net_change"] != entradas - salidas + ajustes
        ):
            raise ValueError(f"Totales inconsistentes en {warehouse_id}")

        total_movimientos += len(movimientos)
        total_entradas += entradas
        total_salidas += salidas
        total_ajustes += ajustes

    if (
        reporte["total_movements"] != total_movimientos
        or reporte["total_entries"] != total_entradas
        or reporte["total_shipments"] != total_salidas
        or reporte["total_adjustments"] != total_ajustes
        or reporte["net_change"]
        != total_entradas - total_salidas + total_ajustes
    ):
        raise ValueError("Totales generales inconsistentes")

    return {
        "report_date": fecha,
        "total_warehouses": 3,
        "total_movements": total_movimientos,
        "total_entries": total_entradas,
        "total_shipments": total_salidas,
        "total_adjustments": total_ajustes,
        "net_change": reporte["net_change"],
    }


def lambda_handler(event, context):
    s3 = boto3.client("s3")
    eventbridge = boto3.client("events")
    bus = os.getenv("EVENT_BUS_NAME", "default")

    procesados = 0
    rechazados = 0

    for record in event.get("Records", []):
        if record.get("eventSource") != "aws:s3":
            continue

        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        if key.startswith("reports/") and key.endswith(".json"):
            metadata = procesar_reporte_contrato(s3, bucket, key, record)
            if metadata["status"] == "INVALID":
                rechazados += 1
            else:
                procesados += 1
            continue
        if not key.startswith("exports/") or not key.endswith(".json"):
            continue

        logger.info("Validando reporte s3://%s/%s", bucket, key)

        # Los errores de acceso a S3 se propagan para que AWS
        # pueda reintentar la invocacion.
        respuesta_s3 = s3.get_object(
            Bucket=bucket,
            Key=key,
        )

        try:
            reporte = json.loads(
                respuesta_s3["Body"].read().decode("utf-8")
            )
            resumen = validar_reporte(reporte)

        except (ValueError, UnicodeDecodeError, TypeError) as error:
            rechazados += 1
            logger.error(
                "Reporte rechazado: s3://%s/%s - %s",
                bucket,
                key,
                error,
            )
            continue

        evento = {
            "bucket": bucket,
            "key": key,
            "report_type": "daily_inventory_movements",
            **resumen,
        }

        respuesta = eventbridge.put_events(
            Entries=[
                {
                    "Source": "warehouse.platform",
                    "DetailType": "InventoryReportCreated",
                    "Detail": json.dumps(evento),
                    "EventBusName": bus,
                }
            ]
        )

        if respuesta.get("FailedEntryCount", 0) > 0:
            raise RuntimeError(
                "No se pudo publicar el evento en EventBridge"
            )

        procesados += 1

        logger.info(
            "Reporte valido y evento publicado: "
            "fecha=%s, movimientos=%d",
            resumen["report_date"],
            resumen["total_movements"],
        )

    resultado = {
        "processed": procesados,
        "rejected": rechazados,
    }

    logger.info("Resultado Lambda: %s", json.dumps(resultado))

    return {
        "statusCode": 200,
        "body": json.dumps(resultado),
    }


def procesar_reporte_contrato(s3, bucket, key, record):
    """Contrato #29: metadata, auditoría de inválidos y registro central autenticado.
    Fallas HTTP/S3 se propagan para permitir reintentos. `metadata/` no activa el trigger.
    """
    response=s3.get_object(Bucket=bucket, Key=key)
    raw=response["Body"].read()
    correlation=(response.get("Metadata") or {}).get("correlation-id") or str(uuid.uuid4())
    digest=hashlib.sha256(raw).hexdigest()
    metadata={"bucket":bucket,"key":key,"correlation_id":correlation,
              "size_bytes":len(raw),"sha256":digest,"status":"VALID","record_count":0}
    try:
        obj=json.loads(raw)
        if not isinstance(obj,dict):raise ValueError("El reporte debe ser un objeto JSON")
        if not obj.get("report_date"):raise ValueError("Falta report_date")
        records=obj.get("movements")
        if records is None:
            records=obj.get("total_movements")
        if isinstance(records,list):metadata["record_count"]=len(records)
        elif type(records)==int and records>=0:metadata["record_count"]=records
        elif isinstance(obj.get("warehouses"),dict):
            metadata["record_count"]=sum(len(v.get("movements",[])) for v in obj["warehouses"].values())
        else:raise ValueError("No se puede calcular el número de registros")
    except (ValueError,TypeError,KeyError) as exc:
        metadata["status"]="INVALID";metadata["reason"]=str(exc)
    path="metadata/"+key
    s3.put_object(Bucket=bucket,Key=path,Body=json.dumps(metadata,ensure_ascii=False).encode(),ContentType="application/json")
    api=os.environ.get("CENTRAL_API_URL","").rstrip("/")
    secret=os.environ.get("CENTRAL_API_KEY","")
    if not api or not secret:
        raise RuntimeError("CENTRAL_API_URL y CENTRAL_API_KEY son obligatorios para registrar reportes")
    req=urllib.request.Request(api+"/internal/reports",data=json.dumps(metadata).encode(),
        headers={"Content-Type":"application/json","X-API-Key":secret,"X-Correlation-ID":correlation},method="POST")
    with urllib.request.urlopen(req,timeout=10) as result:
        if result.status>=300:raise RuntimeError("Registro central rechazado")
    logger.info("Reporte %s: %s, correlation-id=%s, metadata=%s",metadata["status"],key,correlation,path)
    return metadata
