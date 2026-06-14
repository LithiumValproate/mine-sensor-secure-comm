from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from .config_loader import (
    load_default_interval_seconds,
    load_location_list,
    load_sensor_config,
    load_sensor_entry,
    load_sensor_type_unit,
)

DEFAULT_SENSOR_CONFIG = Path(__file__).resolve().parents[2] / 'config' / 'sensors.toml'


@dataclass
class SensorNode:
    """从静态配置初始化的矿井传感器节点。"""

    sensor_id: str
    location: str
    sensor_type: str
    unit: str
    interval_seconds: float

    _next_sequence: ClassVar[int] = 1

    @classmethod
    def from_config(
            cls,
            config_path: str | Path = DEFAULT_SENSOR_CONFIG,
            *,
            sensor_id: str | None = None,
            sensor_type: str | None = None,
            unit: str | None = None,
            interval_sec: float | None = None,
            rng: random.Random | None = None,
    ) -> SensorNode:
        """从 TOML 配置创建传感器节点。

        Args:
            config_path: TOML 传感器配置文件路径。
            sensor_id: 可选的传感器编号；提供时按当前静态配置读取完整传感器条目。
            sensor_type: 传感器类型；仅在未提供 `sensor_id` 时用于模拟生成节点。
            unit: 可选的传感器单位，未提供时按类型从配置读取。
            interval_sec: 可选的采样间隔覆盖值，单位为秒。
            rng: 可选的随机数生成器，用于确定性测试。
        """
        config = load_sensor_config(config_path)

        if sensor_id is not None:
            sensor = load_sensor_entry(
                config,
                sensor_id,
                config_path=config_path,
            )
            resolved_sensor_type = str(sensor['type'])
            resolved_unit = str(
                sensor.get('unit')
                or unit
                or load_sensor_type_unit(
                    config,
                    resolved_sensor_type,
                    config_path=config_path,
                ),
            )
            resolved_location = str(sensor['location'])
            resolved_interval = _normalize_interval(
                sensor.get('interval_seconds', interval_sec if interval_sec is not None else 0.5),
                'interval_seconds',
            )
            if interval_sec is not None:
                resolved_interval = _normalize_interval(
                    interval_sec,
                    'interval_sec',
                )
            return cls(
                sensor_id=sensor_id,
                sensor_type=resolved_sensor_type,
                unit=resolved_unit,
                location=resolved_location,
                interval_seconds=resolved_interval,
            )

        if sensor_type is None:
            raise ValueError('sensor_type is required when sensor_id is not provided')

        locations = load_location_list(
            config,
            config_path=config_path,
        )
        sensor_unit = unit or load_sensor_type_unit(
            config,
            sensor_type,
            config_path=config_path,
        )
        default_interval = load_default_interval_seconds(
            config,
            config_path=config_path,
        )
        interval_seconds = (
            default_interval
            if interval_sec is None
            else _normalize_interval(
                interval_sec,
                'interval_sec',
            )
        )
        chooser = rng if rng is not None else random

        return cls(
            sensor_id=cls._allocate_sensor_id(),
            sensor_type=sensor_type,
            unit=sensor_unit,
            location=chooser.choice(locations),
            interval_seconds=interval_seconds,
        )

    @property
    def interval_sec(self) -> float:
        """返回采样间隔，单位为秒。"""
        return self.interval_seconds

    @interval_sec.setter
    def interval_sec(self, value: float) -> None:
        """设置采样间隔，单位为秒。"""
        self.interval_seconds = _normalize_interval(value, 'interval_sec')

    @classmethod
    def _allocate_sensor_id(cls) -> str:
        """按进程内创建顺序分配下一个传感器 ID。"""
        sequence = cls._next_sequence
        cls._next_sequence += 1
        return f"sensor_{sequence:02d}"


def _normalize_interval(value: Any, name: str) -> float:
    """校验并转换采样间隔值类型。"""
    try:
        interval = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if interval <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return interval
