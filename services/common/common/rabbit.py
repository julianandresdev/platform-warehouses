"""Cliente RabbitMQ síncrono compartido por APIs y workers."""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPConnectionError, NackError, UnroutableError

from common.correlation import correlation_id_context

logger = logging.getLogger(__name__)

Envelope = Mapping[str, Any]
MessageHandler = Callable[[dict[str, Any]], None]

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


def declare_topology(
    channel: BlockingChannel,
    warehouse_ids: tuple[str, ...] = ("WH-001", "WH-002", "WH-003"),
) -> None:
    """Declare the durable exchanges, queues and bindings from docs/events.md.

    Declarations are idempotent. Retry queues and DLQ bindings are completed
    in D-05; until then failed handler deliveries are requeued by ``consume``.
    """

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
            seen_queues.add(queue)
        channel.queue_bind(queue=queue, exchange=exchange, routing_key=binding_key)


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
            headers={"x-attempt": attempt},
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
    """Consume until stopped; ack only after handler returns successfully.

    Handler exceptions are nacked and requeued. D-05 will replace this basic
    policy with transient/permanent classification, retries and a DLQ.
    """

    owns_connection = connection is None
    active_connection = connection or connect(url)
    channel = active_connection.channel()
    try:
        channel.basic_qos(prefetch_count=prefetch_count)
        channel.basic_consume(
            queue=queue,
            on_message_callback=lambda ch, method, properties, body: _deliver(
                ch, method, properties, body, handler
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
) -> None:
    """Decode, set the message correlation context, then ack or requeue."""

    token = None
    try:
        message = json.loads(body)
        if not isinstance(message, dict):
            raise ValueError("El sobre debe ser un objeto JSON")
        correlation_id = message.get("correlation_id") or properties.correlation_id
        token = correlation_id_context.set(correlation_id)
        handler(message)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        logger.exception("rabbit_invalid_message", extra={"queue": method.routing_key})
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return
    except Exception:
        logger.exception("rabbit_handler_failed", extra={"queue": method.routing_key})
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return
    finally:
        if token is not None:
            correlation_id_context.reset(token)
    channel.basic_ack(delivery_tag=method.delivery_tag)
