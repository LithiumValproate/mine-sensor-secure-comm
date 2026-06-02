"""MQTT 消息格式化辅助函数。"""

from __future__ import annotations

import json
import time
from typing import Any


def now_ms() -> int:
    """返回当前 Unix 时间，单位为毫秒。"""
    return int(time.time() * 1000)


def encode_json(data: dict[str, Any]) -> bytes:
    """编码 MQTT JSON 负载。

    Args:
        data: 要编码为 MQTT 负载的 JSON 对象。
    """
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')


def decode_json(payload: bytes | str) -> dict[str, Any]:
    """解码 MQTT JSON 负载。

    Args:
        payload: MQTT 消息体，可以是字节串或字符串。
    """
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError('MQTT payload must be a JSON object')
    return data


def data_topic(sensor_id: str) -> str:
    """返回传感器数据 topic。

    Args:
        sensor_id: 传感器编号。
    """
    return f"mine/{sensor_id}/data"


def status_topic(sensor_id: str) -> str:
    """返回传感器状态 topic。

    Args:
        sensor_id: 传感器编号。
    """
    return f"mine/{sensor_id}/status"


def alert_topic(sensor_id: str) -> str:
    """返回传感器告警 topic。

    Args:
        sensor_id: 传感器编号。
    """
    return f"mine/{sensor_id}/alert"
