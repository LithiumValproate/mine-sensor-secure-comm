"""Ground center validation and alert logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .alerts import Alert, threshold_alert
from .crypto_utils import decrypt_payload
from .replay_guard import ReplayGuard


@dataclass
class ProcessResult:
    """Result of processing one MQTT message."""

    accepted: bool
    plaintext: dict[str, Any] | None = None
    alerts: list[Alert] = field(default_factory=list)


class GroundCenterCore:
    """Pure validation core used by MQTT callbacks and tests."""

    def __init__(
            self,
            *,
            psk_map: dict[str, str],
            sensor_types: dict[str, str],
            thresholds: dict[str, dict[str, float]],
            replay_guard: ReplayGuard | None = None,
    ) -> None:
        self.psk_map = psk_map
        self.sensor_types = sensor_types
        self.thresholds = thresholds
        self.replay_guard = replay_guard or ReplayGuard()

    def process_data_message(
            self,
            payload: dict[str, Any],
            *,
            certificate_identity: str | None,
            receive_time_ms: int,
    ) -> ProcessResult:
        """Validate, decrypt, and inspect one encrypted data payload."""
        sensor_id = str(payload.get('sensor_id', ''))
        sensor_type = str(payload.get('sensor_type', ''))
        alerts: list[Alert] = []

        if sensor_id not in self.psk_map or sensor_id not in self.sensor_types:
            return self._reject('unknown_sensor', sensor_id, {'sensor_id': sensor_id})
        if certificate_identity is not None and certificate_identity != sensor_id:
            return self._reject('identity_mismatch', sensor_id, {
                'certificate_identity': certificate_identity,
                'payload_sensor_id': sensor_id,
            })
        if self.sensor_types[sensor_id] != sensor_type:
            return self._reject('identity_mismatch', sensor_id, {
                'expected_sensor_type': self.sensor_types[sensor_id],
                'payload_sensor_type': sensor_type,
            })

        try:
            seq = int(payload['seq'])
            timestamp_ms = int(payload['timestamp_ms'])
        except (KeyError, TypeError, ValueError):
            return self._reject('invalid_payload', sensor_id, {'reason': 'missing seq or timestamp'})

        replay_error = self.replay_guard.check(sensor_id, seq, timestamp_ms, receive_time_ms)
        if replay_error:
            return self._reject(replay_error, sensor_id, {'seq': seq, 'timestamp_ms': timestamp_ms})

        try:
            plaintext = decrypt_payload(self.psk_map[sensor_id], payload)
        except Exception as exc:
            return self._reject('decrypt_failed', sensor_id, {'error': exc.__class__.__name__})

        self.replay_guard.accept(sensor_id, seq, timestamp_ms, receive_time_ms)
        value = plaintext.get('value')
        if isinstance(value, int | float):
            alert = threshold_alert(sensor_id, sensor_type, float(value), self.thresholds)
            if alert is not None:
                alerts.append(alert)
        return ProcessResult(accepted=True, plaintext=plaintext, alerts=alerts)

    def process_status_message(self, payload: dict[str, Any]) -> ProcessResult:
        """Process online/offline status messages."""
        sensor_id = str(payload.get('sensor_id', ''))
        status = payload.get('status')
        if status == 'offline':
            return ProcessResult(
                accepted=True,
                alerts=[Alert(
                    code='sensor_offline',
                    sensor_id=sensor_id,
                    severity='high',
                    message='sensor unexpectedly disconnected',
                    details=payload,
                )],
            )
        return ProcessResult(accepted=True, plaintext=payload)

    def _reject(self, code: str, sensor_id: str, details: dict[str, Any]) -> ProcessResult:
        return ProcessResult(
            accepted=False,
            alerts=[Alert(
                code=code,
                sensor_id=sensor_id or 'unknown',
                severity='high' if code not in {'timestamp_out_of_window', 'invalid_payload'} else 'medium',
                message=code,
                details=details,
            )],
        )
