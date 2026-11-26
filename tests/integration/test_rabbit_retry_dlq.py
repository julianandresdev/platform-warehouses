"""Pruebas RabbitMQ reales para los reintentos y la DLQ de D-05."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid

import pika
import pytest

from common.rabbit import (
    PermanentError,
    TransientError,
    connect,
    consume,
    dead_letter_queue_name,
    declare_retry_queues,
    retry_queue_name,
)

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
pytestmark = pytest.mark.skipif(not RABBITMQ_URL, reason="define RABBITMQ_URL")


def _wait_for_consumer(channel, queue: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = channel.queue_declare(queue=queue, passive=True).method
        if state.consumer_count:
            return
        time.sleep(0.05)
    pytest.fail(f"no se registró un consumidor para {queue}")


def _start_consumer(queue: str, handler):
    stop_event = threading.Event()
    thread = threading.Thread(
        target=consume,
        kwargs={"queue": queue, "handler": handler, "url": RABBITMQ_URL,
                "stop_event": stop_event},
        daemon=True,
    )
    thread.start()
    return thread, stop_event


def _cleanup(channel, connection, queue: str) -> None:
    for name in (queue, retry_queue_name(queue), dead_letter_queue_name(queue)):
        channel.queue_delete(queue=name, if_unused=False, if_empty=False)
    if connection.is_open:
        connection.close()


def _publish_raw(channel, queue: str, body: bytes) -> None:
    channel.confirm_delivery()
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=body,
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
            headers={"x-attempt": 0},
        ),
        mandatory=True,
    )


def test_invalid_json_goes_directly_to_dlq():
    queue = f"integration.retry.invalid.{uuid.uuid4().hex}"
    connection = connect(RABBITMQ_URL)
    channel = connection.channel()
    channel.queue_declare(queue=queue, durable=False)
    declare_retry_queues(channel, queue)
    called = []
    thread, stop = _start_consumer(queue, lambda message: called.append(message))
    try:
        _wait_for_consumer(channel, queue)
        _publish_raw(channel, queue, b"{invalid json")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            method, properties, _ = channel.basic_get(
                dead_letter_queue_name(queue), auto_ack=True
            )
            if method:
                assert properties.headers["x-attempt"] == 0
                assert "JSON inválido" in properties.headers["x-error"]
                assert called == []
                return
            time.sleep(0.05)
        pytest.fail("el mensaje JSON inválido no llegó a la DLQ")
    finally:
        stop.set()
        thread.join(timeout=5)
        _cleanup(channel, connection, queue)


def test_transient_error_is_retried_three_times_then_dead_lettered():
    queue = f"integration.retry.transient.{uuid.uuid4().hex}"
    connection = connect(RABBITMQ_URL)
    channel = connection.channel()
    channel.queue_declare(queue=queue, durable=False)
    declare_retry_queues(channel, queue)
    attempts = []

    def fail_transiently(message):
        attempts.append(message["event_id"])
        raise TransientError("fallo transitorio simulado")

    thread, stop = _start_consumer(queue, fail_transiently)
    try:
        _wait_for_consumer(channel, queue)
        message = {
            "event_id": str(uuid.uuid4()),
            "event_type": "TEST_RETRY",
            "event_version": 1,
            "occurred_at": "2026-11-26T00:00:00Z",
            "correlation_id": "D05-RETRY-TEST",
            "source": "integration-test",
            "payload": {},
        }
        _publish_raw(channel, queue, json.dumps(message).encode())
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            method, properties, body = channel.basic_get(
                dead_letter_queue_name(queue), auto_ack=True
            )
            if method:
                assert len(attempts) == 3
                assert attempts == [message["event_id"]] * 3
                assert properties.headers["x-attempt"] == 2
                assert "TransientError" in properties.headers["x-error"]
                assert json.loads(body) == message
                return
            time.sleep(0.1)
        pytest.fail("el tercer fallo no envió el mensaje a la DLQ")
    finally:
        stop.set()
        thread.join(timeout=5)
        _cleanup(channel, connection, queue)


def test_permanent_error_goes_directly_to_dlq():
    queue = f"integration.retry.permanent.{uuid.uuid4().hex}"
    connection = connect(RABBITMQ_URL)
    channel = connection.channel()
    channel.queue_declare(queue=queue, durable=False)
    declare_retry_queues(channel, queue)
    attempts = []

    def reject(message):
        attempts.append(message)
        raise PermanentError("evento no soportado")

    thread, stop = _start_consumer(queue, reject)
    try:
        _wait_for_consumer(channel, queue)
        message = {
            "event_id": str(uuid.uuid4()),
            "event_type": "UNKNOWN",
            "event_version": 1,
            "occurred_at": "2026-11-26T00:00:00Z",
            "correlation_id": "D05-PERMANENT-TEST",
            "source": "integration-test",
            "payload": {},
        }
        _publish_raw(channel, queue, json.dumps(message).encode())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            method, properties, _ = channel.basic_get(
                dead_letter_queue_name(queue), auto_ack=True
            )
            if method:
                assert len(attempts) == 1
                assert properties.headers["x-attempt"] == 0
                assert "PermanentError" in properties.headers["x-error"]
                return
            time.sleep(0.05)
        pytest.fail("el error permanente no llegó a la DLQ")
    finally:
        stop.set()
        thread.join(timeout=5)
        _cleanup(channel, connection, queue)
