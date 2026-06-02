"""传感器读数模拟和加密负载生成。"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .crypto_utils import EncryptedPayload, encrypt_payload, new_boot_random
from .message import now_ms


@dataclass
class SensorProfile:
    """静态传感器配置。"""

    sensor_id: str
    sensor_type: str
    unit: str
    location: str
    interval_seconds: float = 1.0


class SensorNodeSimulator:
    """为单个传感器生成读数和加密 MQTT 负载。"""

    def __init__(self, profile: SensorProfile, psk_hex: str) -> None:
        """初始化传感器模拟器。

        Args:
            profile: 传感器静态配置。
            psk_hex: 传感器 PSK 的十六进制字符串。
        """
        self.profile = profile
        self.psk_hex = psk_hex
        self.seq = 0
        self.boot_random = new_boot_random()

    def next_plain_reading(self) -> dict[str, Any]:
        """生成一条模拟读数。"""
        if self.profile.sensor_type == 'gas':
            value = round(max(0.0, random.gauss(0.8, 0.35)), 3)
        elif self.profile.sensor_type == 'temperature':
            value = round(random.gauss(36.0, 6.0), 2)
        else:
            value = round(random.random(), 3)
        return {
            'value': value,
            'unit': self.profile.unit,
            'battery': random.randint(70, 100),
            'location': self.profile.location,
            'sample_time_ms': now_ms(),
        }

    def next_encrypted_payload(self) -> EncryptedPayload:
        """生成并加密一条读数。"""
        timestamp_ms = now_ms()
        payload = encrypt_payload(
            psk_hex=self.psk_hex,
            sensor_id=self.profile.sensor_id,
            sensor_type=self.profile.sensor_type,
            seq=self.seq,
            timestamp_ms=timestamp_ms,
            plaintext=self.next_plain_reading(),
            boot_random=self.boot_random,
        )
        self.seq += 1
        return payload
