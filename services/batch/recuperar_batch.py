
import argparse
import json
import logging
import os

from datetime import date, datetime, timezone
from botocore.exceptions import ClientError

import boto3


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("batch-recovery")


def recuperar_ejecucion(
    cliente_s3,
    bucket,
    fecha,
    edad_minima_minutos=120,
):
    clave = f"batch-runs/{fecha.isoformat()}.json"

    respuesta = cliente_s3.get_object(
        Bucket=bucket,
        Key=clave,
    )

    etag = respuesta["ETag"]
    registro = json.loads(
        respuesta["Body"].read()
    )

    if registro.get("report_date") != fecha.isoformat():
        raise ValueError(
            "La fecha del registro no coincide"
        )

    if registro.get("status") != "RUNNING":
        logger.info(
            "No se necesita recuperacion. Estado: %s",
            registro.get("status"),
        )
        return False

    inicio = datetime.fromisoformat(
        registro["started_at"]
    )

    if inicio.tzinfo is None:
        raise ValueError(
            "El inicio debe incluir zona horaria"
        )

    ahora = datetime.now(timezone.utc)

    antiguedad = (
        ahora - inicio.astimezone(timezone.utc)
    ).total_seconds() / 60

    if antiguedad < edad_minima_minutos:
        raise ValueError(
            "El trabajo es demasiado reciente para recuperarlo"
        )

    registro["status"] = "FAILED"
    registro["finished_at"] = ahora.isoformat()
    registro["error_message"] = (
        "Recuperacion manual de ejecucion interrumpida"
    )

    try:
        cliente_s3.put_object(
            Bucket=bucket,
            Key=clave,
            Body=json.dumps(
                registro,
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8"),
            ContentType="application/json",
            IfMatch=etag,
        )

    except ClientError as error:
        codigo = error.response["Error"]["Code"]

        if codigo in (
            "PreconditionFailed",
            "ConditionalRequestConflict",
            "412",
            "409",
        ):
            raise RuntimeError(
                "El registro cambio durante la recuperacion"
            ) from error

        raise

    logger.info(
        "Ejecucion %s marcada como FAILED",
        fecha.isoformat(),
    )

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Recuperar una ejecucion Batch interrumpida"
    )

    parser.add_argument(
        "--date",
        required=True,
        type=date.fromisoformat,
    )

    parser.add_argument(
        "--min-age-minutes",
        type=int,
        default=120,
    )

    parser.add_argument(
        "--confirm-no-active-job",
        action="store_true",
        help="Confirmar que el trabajo AWS Batch ya termino",
    )

    argumentos = parser.parse_args()

    if argumentos.min_age_minutes < 0:
        parser.error(
            "--min-age-minutes no puede ser negativo"
        )

    if not argumentos.confirm_no_active_job:
        parser.error(
            "Primero verifica en AWS Batch que no existe "
            "una ejecucion activa. Despues utiliza "
            "--confirm-no-active-job."
        )

    cliente_s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
    )

    recuperar_ejecucion(
        cliente_s3,
        os.environ["REPORT_BUCKET"],
        argumentos.date,
        argumentos.min_age_minutes,
    )


if __name__ == "__main__":
    main()
