"""Publish 100 QoS 1 sensors with duplicate, reorder and outage controls."""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import paho.mqtt.client as mqtt
from prometheus_client import Counter, Gauge, start_http_server

from app import config
from app.schemas import SensorType
from app.spool import SensorSpool

logger = logging.getLogger("iot-simulator")
generated_total = Counter("iot_sensor_readings_generated_total", "Unique sensor readings generated")
published_total = Counter("iot_mqtt_publish_ack_total", "MQTT QoS 1 publishes acknowledged")
intentional_duplicates = Counter("iot_simulator_duplicates_total", "Intentional duplicate MQTT publishes")
pending_readings = Gauge("iot_sensor_buffered_readings", "Readings waiting in local store-and-forward buffer")
simulated_outages = Counter("iot_simulated_network_outages_total", "Simulated sensor network outages")

SENSOR_TYPES = tuple(item.value for item in SensorType)


def _reading_value(sensor_type: str) -> float | int:
    if sensor_type == "temperature":
        return round(random.uniform(17.0, 42.0), 2)
    if sensor_type == "humidity":
        return round(random.uniform(25.0, 90.0), 2)
    if sensor_type in {"door", "motion"}:
        return random.randint(0, 1)
    return round(random.uniform(0.1, 8.0), 3)


def _new_client() -> tuple[mqtt.Client, threading.Event]:
    connected = threading.Event()
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"iot-simulator-{uuid4().hex[:12]}",
        clean_session=False,
        protocol=mqtt.MQTTv311,
    )

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            connected.set()
            logger.info("mqtt_connected", extra={"broker": config.MQTT_HOST})
        else:
            logger.error("mqtt_connect_rejected", extra={"reason": str(reason_code)})

    client.on_connect = on_connect
    return client, connected


def _wait_connected(connected: threading.Event, timeout: float = 30) -> None:
    if not connected.wait(timeout):
        raise TimeoutError(f"No se conectó a MQTT en {timeout} segundos")


def _publish(client: mqtt.Client, row: tuple[int, str, int, dict[str, Any]], spool: SensorSpool) -> None:
    row_id, sensor_id, sequence, payload = row
    topic = f"warehouses/{payload['warehouse_id']}/sensors/{sensor_id}"
    encoded = json.dumps(payload, separators=(",", ":"))
    result = client.publish(topic, encoded, qos=1, retain=False)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"MQTT rechazó {sensor_id}:{sequence}, rc={result.rc}")
    result.wait_for_publish(timeout=20)
    if not result.is_published():
        raise TimeoutError(f"MQTT no confirmó {sensor_id}:{sequence}")
    published_total.inc()
    if random.random() < config.DUP_RATE:
        duplicate = client.publish(topic, encoded, qos=1, retain=False)
        if duplicate.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT rechazó el duplicado {sensor_id}:{sequence}")
        duplicate.wait_for_publish(timeout=20)
        if not duplicate.is_published():
            raise TimeoutError(f"MQTT no confirmó el duplicado {sensor_id}:{sequence}")
        published_total.inc()
        intentional_duplicates.inc()
    spool.delete(row_id)
    pending_readings.set(spool.count())


def _generate(
    spool: SensorSpool,
    sensor_id: str,
    warehouse_id: str,
    sensor_type: str,
) -> tuple[int, str, int, dict[str, Any]]:
    sequence = spool.next_sequence(sensor_id)
    now = datetime.now(timezone.utc)
    payload = {
        "event_id": str(uuid4()),
        "warehouse_id": warehouse_id,
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "value": _reading_value(sensor_type),
        "sequence_number": sequence,
        "timestamp": now.isoformat().replace("+00:00", "Z"),
    }
    row_id = spool.add(sensor_id, payload)
    generated_total.inc()
    return row_id, sensor_id, sequence, payload


def _flush_buffer(client: mqtt.Client, spool: SensorSpool) -> None:
    by_sensor: dict[str, list[tuple[int, str, int, dict[str, Any]]]] = defaultdict(list)
    for row in spool.pending():
        by_sensor[row[1]].append(row)
    ordered: list[tuple[int, str, int, dict[str, Any]]] = []
    for rows in by_sensor.values():
        index = 0
        while index < len(rows):
            if index + 1 < len(rows) and random.random() < config.REORDER_RATE:
                ordered.extend((rows[index + 1], rows[index]))
                index += 2
            else:
                ordered.append(rows[index])
                index += 1
    for row in ordered:
        _publish(client, row, spool)


def run() -> dict[str, Any]:
    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))
    start_http_server(9102, addr="0.0.0.0")
    spool = SensorSpool(config.SPOOL_PATH)
    client, connected = _new_client()
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    client.loop_start()
    _wait_connected(connected)

    sensors = []
    for index in range(config.SENSOR_COUNT):
        warehouse_id = config.WAREHOUSE_IDS[index % len(config.WAREHOUSE_IDS)]
        sensor_id = f"sensor-{index + 1:04d}"
        sensor_type = SENSOR_TYPES[index % len(SENSOR_TYPES)]
        sensors.append((sensor_id, warehouse_id, sensor_type))

    started = time.monotonic()
    started_at = datetime.now(timezone.utc)
    outage_start = config.SIMULATED_OUTAGE_START_SECONDS
    outage_end = outage_start + config.SIMULATED_OUTAGE_DURATION_SECONDS
    outage_started = False
    outage_finished = False
    held: dict[str, tuple[int, str, int, dict[str, Any]]] = {}
    buffered_at_outage = 0
    cycle = 0
    next_cycle = started

    try:
        while time.monotonic() - started < config.SIM_DURATION_SECONDS:
            elapsed = time.monotonic() - started
            in_outage = outage_start <= elapsed < outage_end
            if not outage_started and outage_start < config.SIM_DURATION_SECONDS and elapsed >= outage_start:
                logger.warning("sensor_network_outage_started", extra={"elapsed_seconds": round(elapsed, 2)})
                client.disconnect()
                client.loop_stop()
                connected.clear()
                outage_started = True
                simulated_outages.inc()

            if outage_started and not outage_finished and elapsed >= outage_end:
                client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
                client.loop_start()
                _wait_connected(connected)
                logger.warning("sensor_network_recovered", extra={"buffered_readings": spool.count()})
                _flush_buffer(client, spool)
                held.clear()
                outage_finished = True

            current: dict[str, tuple[int, str, int, dict[str, Any]]] = {}
            for sensor_id, warehouse_id, sensor_type in sensors:
                current[sensor_id] = _generate(spool, sensor_id, warehouse_id, sensor_type)

            if not in_outage and not (outage_started and not outage_finished):
                for sensor_id, row in current.items():
                    previous = held.pop(sensor_id, None)
                    if previous is not None:
                        # Send the newer sequence before its buffered predecessor.
                        _publish(client, row, spool)
                        _publish(client, previous, spool)
                    elif random.random() < config.REORDER_RATE:
                        held[sensor_id] = row
                    else:
                        _publish(client, row, spool)
            else:
                pending_readings.set(spool.count())
                if outage_started and not outage_finished and buffered_at_outage == 0:
                    # Count after queuing the first offline batch, not before it.
                    buffered_at_outage = spool.count()

            cycle += 1
            next_cycle += config.PUBLISH_INTERVAL_SECONDS
            wait_for = next_cycle - time.monotonic()
            if wait_for > 0:
                time.sleep(wait_for)

        if outage_started and not outage_finished:
            client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
            client.loop_start()
            _wait_connected(connected)
            outage_finished = True
        _flush_buffer(client, spool)
        ended_at = datetime.now(timezone.utc)
        summary = {
            "started_at": started_at.isoformat(),
            "finished_at": ended_at.isoformat(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "sensor_count": len(sensors),
            "warehouse_ids": list(config.WAREHOUSE_IDS),
            "publish_interval_seconds": config.PUBLISH_INTERVAL_SECONDS,
            "generated_unique": int(generated_total._value.get()),
            "mqtt_publish_acknowledged": int(published_total._value.get()),
            "intentional_duplicate_publishes": int(intentional_duplicates._value.get()),
            "buffered_at_outage_start": buffered_at_outage,
            "buffer_remaining": spool.count(),
            "dup_rate": config.DUP_RATE,
            "reorder_rate": config.REORDER_RATE,
            "simulated_outage_start_seconds": outage_start,
            "simulated_outage_duration_seconds": config.SIMULATED_OUTAGE_DURATION_SECONDS,
            "cycles": cycle,
        }
        summary_path = Path(config.SIMULATOR_SUMMARY_PATH)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        logger.info("simulator_run_completed", extra={"summary": summary})
        return summary
    finally:
        if client.is_connected():
            client.disconnect()
        client.loop_stop()
        spool.close()


if __name__ == "__main__":
    run()

