"""MQTT payload validation and routing helpers."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class SensorType(StrEnum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    DOOR = "door"
    MOTION = "motion"
    ENERGY = "energy"


class SensorReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    warehouse_id: str = Field(pattern=r"^WH-\d{3}$")
    sensor_id: str = Field(min_length=1, max_length=100)
    sensor_type: SensorType
    value: float = Field(allow_inf_nan=False)
    sequence_number: int = Field(ge=1)
    timestamp: AwareDatetime


def topic_for(reading: SensorReading) -> str:
    return f"warehouses/{reading.warehouse_id}/sensors/{reading.sensor_id}"


def routing_key_for(reading: SensorReading) -> str:
    return f"iot.{reading.warehouse_id}.{reading.sensor_type.value}"


def validate_topic(topic: str, reading: SensorReading) -> None:
    parts = topic.split("/")
    if (
        len(parts) != 4
        or parts[0] != "warehouses"
        or parts[2] != "sensors"
        or parts[1] != reading.warehouse_id
        or parts[3] != reading.sensor_id
    ):
        raise ValueError("El tópico MQTT no coincide con el payload")

