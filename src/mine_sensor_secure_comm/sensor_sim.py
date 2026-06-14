"""传感器读数模拟和加密负载生成。"""

from __future__ import annotations

import random
from typing import Any

from .crypto_utils import EncryptedPayload, encrypt_payload, new_boot_random
from .message import now_ms
from .sensor_node import SensorNode


class SensorNodeSimulator:
    """为单个传感器生成读数和加密 MQTT 负载。"""

    def __init__(self, sensor_node: SensorNode, psk_hex: str) -> None:
        """初始化传感器模拟器。

        Args:
            sensor_node: 传感器节点配置。
            psk_hex: 传感器 PSK 的十六进制字符串。
        """
        self.sensor_node = sensor_node
        self.psk_hex = psk_hex
        self.seq = 0
        self.boot_random = new_boot_random()

    def next_plain_reading(self) -> dict[str, Any]:
        """生成一条模拟读数。"""
        if self.sensor_node.sensor_type == 'gas':
            value = round(max(0.0, random.gauss(0.8, 0.35)), 3)
        elif self.sensor_node.sensor_type == 'temperature':
            value = round(random.gauss(36.0, 6.0), 2)
        else:
            value = round(random.random(), 3)
        return {
            'value': value,
            'unit': self.sensor_node.unit,
            'battery': random.randint(70, 100),
            'location': self.sensor_node.location,
            'sample_time_ms': now_ms(),
        }

    def next_encrypted_payload(self) -> EncryptedPayload:
        """生成并加密一条读数。"""
        timestamp_ms = now_ms()
        payload = encrypt_payload(
            psk_hex=self.psk_hex,
            sensor_id=self.sensor_node.sensor_id,
            sensor_type=self.sensor_node.sensor_type,
            seq=self.seq,
            timestamp_ms=timestamp_ms,
            plaintext=self.next_plain_reading(),
            boot_random=self.boot_random,
        )
        self.seq += 1
        return payload
