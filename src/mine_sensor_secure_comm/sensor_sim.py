"""Sensor reading simulation and encrypted payload creation."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .crypto_utils import EncryptedPayload, encrypt_payload, new_boot_random
from .message import now_ms


@dataclass
class SensorProfile:
    """Static sensor configuration."""

    sensor_id: str
    sensor_type: str
    unit: str
    location: str
    interval_seconds: float = 1.0


class SensorNodeSimulator:
    """Generate readings and encrypted MQTT payloads for one sensor."""

    def __init__(self, profile: SensorProfile, psk_hex: str) -> None:
        self.profile = profile
        self.psk_hex = psk_hex
        self.seq = 0
        self.boot_random = new_boot_random()

    def next_plain_reading(self) -> dict[str, Any]:
        """Generate one simulated reading."""
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
        """Generate and encrypt one reading."""
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
