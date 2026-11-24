"""Abstraccion simple para S3 y MinIO, configurable por entorno."""
import json
import os
import boto3


def client():
    endpoint = os.getenv("S3_ENDPOINT_URL") or None
    return boto3.client("s3", endpoint_url=endpoint)


def write_json(bucket, key, obj, *, correlation_id=None, s3=None):
    data = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    args = {"Bucket": bucket, "Key": key, "Body": data, "ContentType": "application/json"}
    if correlation_id:
        args["Metadata"] = {"correlation-id": str(correlation_id)}
    (s3 or client()).put_object(**args)
    return key


def read_json(bucket, key, *, s3=None):
    obj=(s3 or client()).get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read())
