"""Cliente RabbitMQ síncrono compartido por APIs y workers."""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from copy import copy
from collections.abc import Callable, Mapping
from typing import Any

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPConnectionError, NackError, UnroutableError

from common.correlation import reset_correlation_id, set_correlation_id

logger = logging.getLogger(__name__)

Envelope = Mapping[str, Any]
MessageHandler = Callable[[dict[str, Any]], None]
MAX_DELIVERY_ATTEMPTS = 3
RETRY_TTL_MS = 5_000


class TransientError(RuntimeError):
    """Error temporal del que vale la pena volver a intentar el mensaje."""


class PermanentError(ValueError):
    """Mensaje inválido o no soportado que no debe reintentarse."""


def retry_queue_name(queue: str) -> str:
    return f"{queue}.retry"


def dead_letter_queue_name(queue: str) -> str:
    return f"{queue}.dlq"

EXCHANGES: dict[str, str] = {
    "warehouse.events": "topic",
    "central.events": "topic",
    "warehouse.commands": "direct",
    "iot.readings": "topic",
    "dlx": "direct",
}


def _queue_specs(warehouse_ids: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """Produce (queue, exchange, binding key) declarations."""

    specs: list[tuple[str, str, str]] = []
    for warehouse_id in warehouse_ids:
        prefix = warehouse_id.lower()
        warehouse_key = warehouse_id
        event_prefix = f"warehouse.{warehouse_id}"
        specs.extend(
            [
                (f"{prefix}.commands", "warehouse.commands", warehouse_key),
                (
                    f"{prefix}.cache-invalidation",
                    "warehouse.events",
                    f"{event_prefix}.inventory.updated",
                ),
                (
                    f"{prefix}.reports",
                    "warehouse.events",
                    f"{event_prefix}.report.requested",
                ),
            ]
        )
    specs.extend(
        [
            ("central.projection", "warehouse.events", "warehouse.*.inventory.updated"),
            ("central.projection", "warehouse.events", "warehouse.*.heartbeat"),
            ("central.transfer-orchestrator", "warehouse.events", "warehouse.*.transfer.*"),
            ("central.audit", "warehouse.events", "#"),
            ("central.audit", "central.events", "#"),
            ("iot.storage", "iot.readings", "iot.#"),
            ("iot.alerts", "iot.readings", "iot.*.temperature"),
        ]
    )
    return specs


def work_queue_names(
    warehouse_ids: tuple[str, ...] = ("WH-001", "WH-002", "WH-003"),
) -> tuple[str, ...]:
    """Return the unique durable work queues in the shared topology."""

    return tuple(dict.fromkeys(queue for queue, _, _ in _queue_specs(warehouse_ids)))


def declare_topology(
    channel: BlockingChannel,
    warehouse_ids: tuple[str, ...] = ("WH-001", "WH-002", "WH-003"),
) -> None:
    """Declare the durable exchanges, work queues, retry queues and DLQs."""

    channel.exchange_declare(exchange="dlx", exchange_type="direct", durable=True)
    for exchange, exchange_type in EXCHANGES.items():
        channel.exchange_declare(
            exchange=exchange, exchange_type=exchange_type, durable=True
        )

    seen_queues: set[str] = set()
    for queue, exchange, binding_key in _queue_specs(warehouse_ids):
        if queue not in seen_queues:
            channel.queue_declare(
                queue=queue,
                durable=True,
                arguments={"x-dead-letter-exchange": "dlx"},
            )
            declare_retry_queues(channel, queue)
            seen_queues.add(queue)
        channel.queue_bind(queue=queue, exchange=exchange, routing_key=binding_key)


def declare_retry_queues(channel: BlockingChannel, queue: str) -> None:
    """Declare a queue's fixed-delay retry path and durable dead-letter queue."""

    channel.queue_declare(
        queue=retry_queue_name(queue),
        durable=True,
        arguments={
            "x-message-ttl": RETRY_TTL_MS,
            # The default exchange routes by queue name after the TTL expires.
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": queue,
        },
    )
    channel.queue_declare(queue=dead_letter_queue_name(queue), durable=True)


def connect(
    url: str | None = None,
    *,
    attempts: int = 5,
    initial_delay: float = 0.5,
    max_delay: float = 8.0,
) -> pika.BlockingConnection:
    """Connect with bounded exponential backoff and jitter."""

    connection_url = url or os.getenv(
        "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F"
    )
    if attempts < 1:
        raise ValueError("attempts debe ser al menos 1")

    delay = initial_delay
    for attempt in range(1, attempts + 1):
        try:
            params = pika.URLParameters(connection_url)
            params.heartbeat = 30
            params.blocked_connection_timeout = 30
            return pika.BlockingConnection(params)
        except AMQPConnectionError:
            if attempt == attempts:
                raise
            sleep_for = min(delay, max_delay) + random.uniform(0, min(delay, 0.25))
            logger.warning(
                "rabbit_connection_retry",
                extra={"attempt": attempt, "delay_seconds": round(sleep_for, 3)},
            )
            time.sleep(sleep_for)
            delay = min(delay * 2, max_delay)
    raise RuntimeError("No se pudo establecer la conexión RabbitMQ")


def _envelope_dict(envelope: Envelope | Any) -> dict[str, Any]:
    if hasattr(envelope, "model_dump"):
        data = envelope.model_dump(mode="json")
    elif isinstance(envelope, Mapping):
        data = dict(envelope)
    else:
        raise TypeError("envelope debe ser un mapping o un modelo Pydantic")
    required = {
        "event_id",
        "event_type",
        "event_version",
        "occurred_at",
        "correlation_id",
        "source",
        "payload",
    }
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Faltan campos del sobre: {', '.join(sorted(missing))}")
    return data


def publish(
    envelope: Envelope | Any,
    exchange: str,
    routing_key: str,
    *,
    channel: BlockingChannel | None = None,
    url: str | None = None,
    attempt: int = 0,
) -> None:
    """Publish persistent JSON and require a broker confirm.

    Pass a reusable channel for worker relays; otherwise this function opens
    and closes its own connection, which is convenient for occasional sends.
    """

    data = _envelope_dict(envelope)
    owns_connection = channel is None
    if channel is None:
        connection = connect(url)
        active_channel = connection.channel()
    else:
        connection = None
        active_channel = channel
    try:
        if not getattr(active_channel, "_warehouse_publisher_confirms", False):
            active_channel.confirm_delivery()
            active_channel._warehouse_publisher_confirms = True
        properties = pika.BasicProperties(
            message_id=str(data["event_id"]),
            correlation_id=data["correlation_id"],
            content_type="application/json",
            delivery_mode=2,
            headers={"x-attempt": max(0, int(attempt))},
        )
        try:
            confirmed = active_channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                properties=properties,
                mandatory=True,
            )
        except (NackError, UnroutableError) as exc:
            raise RuntimeError("RabbitMQ rechazó o no pudo enrutar el mensaje") from exc
        if confirmed is False:
            raise RuntimeError("RabbitMQ no confirmó la publicación")
    finally:
        if owns_connection and connection is not None and connection.is_open:
            connection.close()


def consume(
    queue: str,
    handler: MessageHandler,
    *,
    connection: pika.BlockingConnection | None = None,
    url: str | None = None,
    prefetch_count: int = 10,
    stop_event: threading.Event | None = None,
) -> None:
    """Consume with bounded retries; ack only after processing or safe reroute."""

    owns_connection = connection is None
    active_connection = connection or connect(url)
    channel = active_connection.channel()
    try:
        declare_retry_queues(channel, queue)
        channel.basic_qos(prefetch_count=prefetch_count)
        channel.basic_consume(
            queue=queue,
            on_message_callback=lambda ch, method, properties, body: _deliver(
                ch, method, properties, body, handler, queue
            ),
            auto_ack=False,
        )
        if stop_event is None:
            channel.start_consuming()
        else:
            while channel.is_open and not stop_event.is_set():
                active_connection.process_data_events(time_limit=0.5)
            if channel.is_open:
                channel.stop_consuming()
    except KeyboardInterrupt:
        if channel.is_open:
            channel.stop_consuming()
    finally:
        if owns_connection and active_connection.is_open:
            active_connection.close()


def _deliver(
    channel: BlockingChannel,
    method: pika.spec.Basic.Deliver,
    properties: pika.BasicProperties,
    body: bytes,
    handler: MessageHandler,
    queue: str,
) -> None:
    """Decode and handle one delivery, routing failures safely before ack."""

    token = None
    try:
        message = json.loads(body)
        if not isinstance(message, dict):
            raise PermanentError("El sobre debe ser un objeto JSON")
        correlation_id = message.get("correlation_id") or properties.correlation_id
        token = set_correlation_id(correlation_id)
        handler(message)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _route_failure(
            channel,
            method,
            properties,
            body,
            queue,
            PermanentError(f"JSON inválido: {exc}"),
        )
        return
    except PermanentError as exc:
        _route_failure(channel, method, properties, body, queue, exc)
        return
    except Exception as exc:
        _route_failure(channel, method, properties, body, queue, exc)
        return
    finally:
        if token is not None:
            reset_correlation_id(token)
    channel.basic_ack(delivery_tag=method.delivery_tag)


def _route_failure(
    channel: BlockingChannel,
    method: pika.spec.Basic.Deliver,
    properties: pika.BasicProperties,
    body: bytes,
    queue: str,
    error: Exception,
) -> None:
    """Publish to retry/DLQ with confirms, then ack the original delivery."""

    headers = dict(properties.headers or {})
    try:
        attempt = max(0, int(headers.get("x-attempt", 0)))
    except (TypeError, ValueError):
        attempt = 0

    permanent = isinstance(error, PermanentError)
    exhausted = attempt >= MAX_DELIVERY_ATTEMPTS - 1
    to_dlq = permanent or exhausted
    target = dead_letter_queue_name(queue) if to_dlq else retry_queue_name(queue)

    if to_dlq:
        headers["x-error"] = f"{type(error).__name__}: {error}"[:1_000]
    else:
        headers["x-attempt"] = attempt + 1
        headers.pop("x-error", None)

    try:
        _publish_raw_to_queue(channel, target, body, properties, headers)
    except Exception:
        logger.exception(
            "rabbit_failure_route_failed",
            extra={"queue": queue, "target": target, "message_id": properties.message_id},
        )
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return

    logger.warning(
        "rabbit_message_dead_lettered" if to_dlq else "rabbit_message_retry_scheduled",
        extra={
            "queue": queue,
            "target": target,
            "attempt": attempt,
            "error": f"{type(error).__name__}: {error}",
            "message_id": properties.message_id,
        },
    )
    channel.basic_ack(delivery_tag=method.delivery_tag)


def _publish_raw_to_queue(
    channel: BlockingChannel,
    queue: str,
    body: bytes,
    properties: pika.BasicProperties,
    headers: dict[str, Any],
) -> None:
    """Republish raw JSON to a durable queue and wait for broker confirmation."""

    if not getattr(channel, "_warehouse_publisher_confirms", False):
        channel.confirm_delivery()
        channel._warehouse_publisher_confirms = True
    cloned_properties = copy(properties)
    cloned_properties.headers = headers
    cloned_properties.delivery_mode = 2
    cloned_properties.expiration = None
    confirmed = channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=body,
        properties=cloned_properties,
        mandatory=True,
    )
    if confirmed is False:
        raise RuntimeError("RabbitMQ no confirmó el reencaminamiento")
