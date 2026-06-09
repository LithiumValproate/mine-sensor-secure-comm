from __future__ import annotations

import random
import tomllib
from dataclasses import dataclass
from typing import Any

from .crypto_utils import EncryptedPayload, encrypt_payload, new_boot_random
from .message import now_ms


@dataclass
class SensorNode:
    """传感器节点类

    Attributes:
        sensor_id: 传感器 ID
        location: 传感器位置
        interval_seconds: 传感器采集间隔，单位为秒
    """

    sensor_id: str
    location: str
    interval_seconds: float = 0.5
