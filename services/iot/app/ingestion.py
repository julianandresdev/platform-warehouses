"""MQTT gateway that validates readings and republishes to RabbitMQ."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

import pika
import paho.mqtt.client as mqtt
from prometheus_client import Counter, Histogram, start_http_server
from pydantic import ValidationError

from common.events import EventEnvelope
from common.rabbit import connect, declare_retry_queues, declare_topology, publish
from app import config
from app.schemas import SensorReading, routing_key_for, validate_topic

logger = logging.getLogger("iot-ingestion")
mqtt_received = Counter("iot_mqtt_readings_received_total", "MQTT readings received")
rabbit_published = Counter("iot_rabbit_readings_published_total", "Readings confirmed by RabbitMQ")
invalid_dead_lettered = Counter("iot_invalid_readings_dead_lettered_total", "Invalid MQTT readings sent to DLQ")
rabbit_publish_retries = Counter("iot_rabbit_publish_retries_total", "RabbitMQ publication retries")
ingestion_latency = Histogram(
    "iot_ingestion_latency_seconds",
    "Time from sensor sample to RabbitMQ publication",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)


class RabbitPublisher:
    def __init__(self) -> None:
        self.connection = None
        self.channel = None
        self.lock = threading.Lock()

    def _connect(self) -> None:
        self.connection = connect(config.RABBITMQ_URL, attempts=5)
        self.channel = self.connection.channel()
        declare_topology(self.channel)
        declare_retry_queues(self.channel, "iot.ingestion")

    def _ensure_channel(self) -> None:
        if (
            self.connection is None
            or not self.connection.is_open
            or self.channel is None
            or not self.channel.is_open
        ):
            self._connect()

    def _retry(self, operation) -> None:
        delay = 0.5
        while True:
            try:
                with self.lock:
                    self._ensure_channel()
                    operation(self.channel)
                return
            except Exception:
                rabbit_publish_retries.inc()
                logger.exception("iot_rabbit_publish_failed_retrying")
                self.close()
                time.sleep(delay)
                delay = min(delay * 2, 10)

    def publish_reading(self, event: EventEnvelope, routing_key: str) -> None:
        self._retry(
            lambda channel: publish(
                event, "iot.readings", routing_key, channel=channel
            )
        )

    def dead_letter(self, topic: str, body: bytes, error: Exception) -> None:
        def _publish(channel) -> None:
            if not getattr(channel, "_warehouse_publisher_confirms", False):
                channel.confirm_delivery()
                channel._warehouse_publisher_confirms = True
            properties = pika.BasicProperties(
                message_id=f"mqtt-invalid-{uuid4()}",
                content_type="application/json",
                delivery_mode=2,
                headers={"x-error": f"{type(error).__name__}: {error}"[:1_000], "mqtt-topic": topic},
            )
            confirmed = channel.basic_publish(
                exchange="",
                routing_key="iot.ingestion.dlq",
                body=body,
                properties=properties,
                mandatory=True,
            )
            if confirmed is False:
                raise RuntimeError("RabbitMQ no confirmó el envío del mensaje inválido a DLQ")

        self._retry(_publish)

    def close(self) -> None:
        if self.connection is not None and self.connection.is_open:
            try:
                self.connection.close()
            except Exception:
                logger.exception("iot_rabbit_close_failed")
        self.connection = None
        self.channel = None


def handle_mqtt_message(
    client: mqtt.Client,
    message: mqtt.MQTTMessage,
    publisher: RabbitPublisher,
) -> None:
    mqtt_received.inc()
    try:
        reading = SensorReading.model_validate_json(message.payload)
        validate_topic(message.topic, reading)
        event = EventEnvelope(
            event_id=reading.event_id,
            event_type="SENSOR_READING",
            event_version=1,
            occurred_at=reading.timestamp,
            correlation_id=str(reading.event_id),
            source=f"iot-gateway-{reading.warehouse_id}",
            payload=reading.model_dump(mode="json"),
        )
        publisher.publish_reading(event, routing_key_for(reading))
        latency = (datetime.now(timezone.utc) - reading.timestamp).total_seconds()
        ingestion_latency.observe(max(0.0, latency))
        rabbit_published.inc()
    except (ValidationError, ValueError, UnicodeDecodeError) as exc:
        publisher.dead_letter(message.topic, message.payload, exc)
        invalid_dead_lettered.inc()
    client.ack(message.mid, message.qos)


def run() -> None:
    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))
    start_http_server(9103, addr="0.0.0.0")
    publisher = RabbitPublisher()
    publisher._retry(lambda channel: None)
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"iot-ingestion-{uuid4().hex[:10]}",
        clean_session=False,
        protocol=mqtt.MQTTv311,
    )
    client.manual_ack_set(True)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            result, _ = client.subscribe("warehouses/+/sensors/+", qos=1)
            if result != mqtt.MQTT_ERR_SUCCESS:
                logger.error("mqtt_subscribe_failed", extra={"result": result})
            else:
                logger.info("iot_ingestion_subscribed", extra={"topic": "warehouses/+/sensors/+"})
        else:
            logger.error("mqtt_ingestion_connect_rejected", extra={"reason": str(reason_code)})

    client.on_connect = on_connect
    client.on_message = lambda active_client, userdata, message: handle_mqtt_message(
        active_client, message, publisher
    )
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    try:
        client.loop_forever(retry_first_connection=True)
    finally:
        publisher.close()


if __name__ == "__main__":
    run()

