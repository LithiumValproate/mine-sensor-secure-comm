"""告警模型和阈值检查。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Alert:
    """中心端告警事件。"""

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
    """根据解密后的传感器读数返回阈值告警。

    Args:
        sensor_id: 传感器编号。
        sensor_type: 传感器类型，用于查找对应阈值。
        value: 解密后的传感器数值。
        thresholds: 按传感器类型组织的 warning/critical 阈值配置。
    """
    sensor_threshold = thresholds.get(sensor_type, {})
    critical = sensor_threshold.get('critical')
    warning = sensor_threshold.get('warning')
    if critical is not None and value >= critical:
        return Alert(
            code=f"{sensor_type}_threshold_exceeded",
            sensor_id=sensor_id,
            severity='high',
            message=f"{sensor_type} critical threshold exceeded",
            details={'value': value, 'threshold': critical},
        )
    if warning is not None and value >= warning:
        return Alert(
            code=f"{sensor_type}_threshold_warning",
            sensor_id=sensor_id,
            severity='medium',
            message=f"{sensor_type} warning threshold exceeded",
            details={'value': value, 'threshold': warning},
        )
    return None
