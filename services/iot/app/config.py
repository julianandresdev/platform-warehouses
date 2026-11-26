"""Validated environment settings for the IoT services."""

from __future__ import annotations

import os


def integer(name: str, default: int, *, minimum: int = 0) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} debe ser >= {minimum}")
    return value


def number(name: str, default: float, *, minimum: float = 0.0) -> float:
    value = float(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} debe ser >= {minimum}")
    return value


def rate(name: str, default: float) -> float:
    value = number(name, default)
    if value > 1:
        raise ValueError(f"{name} debe estar entre 0 y 1")
    return value


def warehouses() -> tuple[str, ...]:
    values = tuple(
        item.strip()
        for item in os.getenv(
            "WAREHOUSE_IDS", "WH-001,WH-002,WH-003,WH-004,WH-005"
        ).split(",")
        if item.strip()
    )
    if not values or any(not item.startswith("WH-") for item in values):
        raise ValueError("WAREHOUSE_IDS debe incluir identificadores WH válidos")
    return values


MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = integer("MQTT_PORT", 1883, minimum=1)
MQTT_KEEPALIVE = integer("MQTT_KEEPALIVE", 60, minimum=1)
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://iot:iot@iot-db:5432/iot"
)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

SENSOR_TYPES = ("temperature", "humidity", "door", "motion", "energy")
WAREHOUSE_IDS = warehouses()
SENSOR_COUNT = integer("SENSOR_COUNT", 100, minimum=1)
PUBLISH_INTERVAL_SECONDS = number("PUBLISH_INTERVAL_SECONDS", 2.0, minimum=0.05)
SIM_DURATION_SECONDS = integer("SIM_DURATION_SECONDS", 600, minimum=1)
DUP_RATE = rate("DUP_RATE", 0.02)
REORDER_RATE = rate("REORDER_RATE", 0.05)
SIMULATED_OUTAGE_START_SECONDS = integer(
    "SIMULATED_OUTAGE_START_SECONDS", 60, minimum=0
)
SIMULATED_OUTAGE_DURATION_SECONDS = integer(
    "SIMULATED_OUTAGE_DURATION_SECONDS", 20, minimum=0
)
SPOOL_PATH = os.getenv("SPOOL_PATH", "/var/lib/iot-spool/spool.sqlite3")
SIMULATOR_SUMMARY_PATH = os.getenv(
    "SIMULATOR_SUMMARY_PATH", "/evidence/simulacion-10min.json"
)
TEMPERATURE_THRESHOLD = number("TEMPERATURE_THRESHOLD", 35.0)

