
import json
import logging
from datetime import datetime, timezone

from botocore.exceptions import ClientError

logger = logging.getLogger("warehouse-batch")


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _clave(fecha):
    return f"batch-runs/{fecha.isoformat()}.json"


def _leer(s3, bucket, clave):
    try:
        respuesta = s3.get_object(Bucket=bucket, Key=clave)
    except ClientError as error:
        codigo = error.response["Error"]["Code"]
        if codigo in ("NoSuchKey", "404", "NotFound"):
            return None, None
        raise

    datos = json.loads(respuesta["Body"].read())
    return datos, respuesta["ETag"]


def _guardar(s3, bucket, clave, datos, condicion):
    contenido = json.dumps(
        datos, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")

    return s3.put_object(
        Bucket=bucket,
        Key=clave,
        Body=contenido,
        ContentType="application/json",
        **condicion,
    )["ETag"]


def iniciar_ejecucion(s3, bucket, fecha):
    clave = _clave(fecha)
    anterior, etag = _leer(s3, bucket, clave)

    if anterior is not None:
        if anterior["status"] in ("RUNNING", "SUCCEEDED"):
            logger.info(
                "La fecha %s ya esta en proceso o completada",
                fecha,
            )
            return None

        if anterior["status"] != "FAILED":
            raise ValueError("Estado de ejecución desconocido")

    datos = {
        "report_date": fecha.isoformat(),
        "status": "RUNNING",
        "started_at": _ahora(),
        "finished_at": None,
        "s3_key": None,
        "error_message": None,
        "attempt_count": (
            anterior["attempt_count"] + 1
            if anterior else 1
        ),
    }

    condicion = (
        {"IfMatch": etag}
        if etag else {"IfNoneMatch": "*"}
    )

    try:
        nuevo_etag = _guardar(
            s3, bucket, clave, datos, condicion
        )
    except ClientError as error:
        codigo = error.response["Error"]["Code"]
        if codigo in (
            "PreconditionFailed",
            "ConditionalRequestConflict",
            "412",
            "409",
        ):
            logger.info(
                "Otra ejecución modificó el registro de %s",
                fecha,
            )
            return None
        raise

    return {"clave": clave, "etag": nuevo_etag, "datos": datos}


def finalizar_ejecucion(s3, bucket, registro, s3_key):
    datos = dict(registro["datos"])
    datos.update({
        "status": "SUCCEEDED",
        "finished_at": _ahora(),
        "s3_key": s3_key,
        "error_message": None,
    })

    _guardar(
        s3,
        bucket,
        registro["clave"],
        datos,
        {"IfMatch": registro["etag"]},
    )


def registrar_error(s3, bucket, registro, error):
    datos = dict(registro["datos"])
    datos.update({
        "status": "FAILED",
        "finished_at": _ahora(),
        "error_message": str(error)[:2000],
    })

    _guardar(
        s3,
        bucket,
        registro["clave"],
        datos,
        {"IfMatch": registro["etag"]},
    )
