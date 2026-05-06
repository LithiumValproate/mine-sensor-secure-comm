"""Alert model and threshold checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Alert:
    """Center-side alert event."""

    code: str
    sensor_id: str
    severity: str
    message: str
    details: dict[str, Any]


def threshold_alert(
    sensor_id: str,
    sensor_type: str,
    value: float,
    thresholds: dict[str, dict[str, float]],
) -> Alert | None:
    """Return threshold alert for a decrypted sensor reading."""
    sensor_threshold = thresholds.get(sensor_type, {})
    critical = sensor_threshold.get('critical')
    warning = sensor_threshold.get('warning')
    if critical is not None and value >= critical:
        return Alert(
            code=f'{sensor_type}_threshold_exceeded',
            sensor_id=sensor_id,
            severity='high',
            message=f'{sensor_type} critical threshold exceeded',
            details={'value': value, 'threshold': critical},
        )
    if warning is not None and value >= warning:
        return Alert(
            code=f'{sensor_type}_threshold_warning',
            sensor_id=sensor_id,
            severity='medium',
            message=f'{sensor_type} warning threshold exceeded',
            details={'value': value, 'threshold': warning},
        )
    return None
