
import json
import logging
import os
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    eventbridge = boto3.client("events")
    bus = os.getenv("EVENT_BUS_NAME", "default")

    procesados = 0

    for record in event.get("Records", []):
        if record.get("eventSource") != "aws:s3":
            continue

        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        if not key.startswith("exports/"):
            continue

        evento = {
            "bucket": bucket,
            "key": key,
            "event_name": record.get("eventName"),
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

        logger.info(
            "Reporte procesado: s3://%s/%s",
            bucket,
            key,
        )

        procesados += 1

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": procesados}),
    }
