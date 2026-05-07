"""MQTT message formatting helpers."""

from __future__ import annotations

import json
import time
from typing import Any


def now_ms() -> int:
    """Return current Unix time in milliseconds."""
    return int(time.time() * 1000)


def encode_json(data: dict[str, Any]) -> bytes:
    """Encode JSON payload for MQTT."""
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')


def decode_json(payload: bytes | str) -> dict[str, Any]:
    """Decode MQTT JSON payload."""
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError('MQTT payload must be a JSON object')
    return data


def data_topic(sensor_id: str) -> str:
    """Return sensor data topic."""
    return f"mine/{sensor_id}/data"


def status_topic(sensor_id: str) -> str:
    """Return sensor status topic."""
    return f"mine/{sensor_id}/status"


def alert_topic(sensor_id: str) -> str:
    """Return sensor alert topic."""
    return f"mine/{sensor_id}/alert"
