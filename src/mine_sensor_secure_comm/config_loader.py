"""配置加载辅助函数。"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    """从磁盘加载 JSON 对象。

    Args:
        path: JSON 配置文件路径。
    """
    with Path(path).open('r', encoding='utf-8') as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def load_toml(path: str | Path) -> dict[str, Any]:
    """从磁盘加载 TOML 对象。

    Args:
        path: TOML 配置文件路径。
    """
    with Path(path).open('rb') as config_file:
        data = tomllib.load(config_file)
    if not isinstance(data, dict):
        raise ValueError(f"expected TOML object in {path}")
    return data


def load_sensor_config(path: str | Path) -> dict[str, Any]:
    """按文件后缀加载传感器配置文件。

    Args:
        path: 传感器配置文件路径。
    """
    config_path = Path(path)
    return load_toml(config_path)


def load_sensor_map(
        sensor_config: dict[str, Any],
        *,
        config_path: str | Path = '<memory>',
) -> dict[str, dict[str, Any]]:
    """读取并校验按传感器 ID 组织的配置映射。

    Args:
        sensor_config: 已加载的传感器配置对象。
        config_path: 配置来源路径，仅用于错误信息。
    """
    sensors = sensor_config.get('sensors', {})
    if not isinstance(sensors, dict):
        raise ValueError(f"invalid sensors section in {config_path}")

    sensor_map: dict[str, dict[str, Any]] = {}
    for sensor_id, entry in sensors.items():
        if not isinstance(entry, dict):
            raise ValueError(f"invalid sensor entry for {sensor_id} in {config_path}")
        sensor_map[str(sensor_id)] = entry
    return sensor_map


def load_sensor_entry(
        sensor_config: dict[str, Any],
        sensor_id: str,
        *,
        config_path: str | Path = '<memory>',
) -> dict[str, Any]:
    """读取单个传感器配置，不存在时给出明确错误。

    Args:
        sensor_config: 已加载的传感器配置对象。
        sensor_id: 要查找的传感器编号。
        config_path: 配置来源路径，仅用于错误信息。
    """
    sensor_map = load_sensor_map(
        sensor_config,
        config_path=config_path,
    )
    sensor = sensor_map.get(sensor_id)
    if sensor is None:
        raise ValueError(f"sensor_id not found in sensor config: {sensor_id}")
    return sensor


def load_sensor_type_map(
        sensor_config: dict[str, Any],
        *,
        config_path: str | Path = '<memory>',
) -> dict[str, dict[str, Any]]:
    """读取并校验按传感器类型组织的配置映射。

    Args:
        sensor_config: 已加载的传感器配置对象。
        config_path: 配置来源路径，仅用于错误信息。
    """
    sensor_types = sensor_config.get('sensor_types', {})
    if not isinstance(sensor_types, dict):
        raise ValueError(f"invalid sensor_types section in {config_path}")

    sensor_type_map: dict[str, dict[str, Any]] = {}
    for sensor_type, entry in sensor_types.items():
        if not isinstance(entry, dict):
            raise ValueError(f"invalid sensor type entry for {sensor_type} in {config_path}")
        sensor_type_map[str(sensor_type)] = entry
    return sensor_type_map


def load_threshold_map(
        sensor_config: dict[str, Any],
        *,
        config_path: str | Path = '<memory>',
) -> dict[str, dict[str, float]]:
    """从 `sensor_types` 配置中派生阈值映射。

    Args:
        sensor_config: 已加载的传感器配置对象。
        config_path: 配置来源路径，仅用于错误信息。
    """
    threshold_map: dict[str, dict[str, float]] = {}
    for sensor_type, entry in load_sensor_type_map(
        sensor_config,
        config_path=config_path,
    ).items():
        thresholds: dict[str, float] = {}
        for source_key, target_key in (
            ('warning_threshold', 'warning'),
            ('critical_threshold', 'critical'),
        ):
            value = entry.get(source_key)
            if value is None:
                continue
            if not isinstance(value, int | float):
                raise ValueError(f"{source_key} for {sensor_type} must be numeric in {config_path}")
            thresholds[target_key] = float(value)
        threshold_map[sensor_type] = thresholds
    return threshold_map


def load_sensor_type_unit(
        sensor_config: dict[str, Any],
        sensor_type: str,
        *,
        config_path: str | Path = '<memory>',
) -> str:
    """按传感器类型读取默认单位。

    Args:
        sensor_config: 已加载的传感器配置对象。
        sensor_type: 传感器类型。
        config_path: 配置来源路径，仅用于错误信息。
    """
    sensor_type_entry = load_sensor_type_map(
        sensor_config,
        config_path=config_path,
    ).get(sensor_type)
    if sensor_type_entry is None:
        raise ValueError(f"sensor type {sensor_type} missing in {config_path}")
    unit = sensor_type_entry.get('unit')
    if not isinstance(unit, str):
        raise ValueError(f"unit for {sensor_type} missing in {config_path}")
    return unit


def load_location_list(
        sensor_config: dict[str, Any],
        *,
        config_path: str | Path = '<memory>',
) -> list[str]:
    """读取候选位置列表。

    Args:
        sensor_config: 已加载的传感器配置对象。
        config_path: 配置来源路径，仅用于错误信息。
    """
    locations = sensor_config.get('locations')
    if not isinstance(locations, list) or not locations:
        raise ValueError(f"locations must be a non-empty list in {config_path}")
    if not all(isinstance(location, str) for location in locations):
        raise ValueError(f"locations must contain only strings in {config_path}")
    return locations


def load_default_interval_seconds(
        sensor_config: dict[str, Any],
        *,
        config_path: str | Path = '<memory>',
) -> float:
    """读取默认采样间隔。

    Args:
        sensor_config: 已加载的传感器配置对象。
        config_path: 配置来源路径，仅用于错误信息。
    """
    value = sensor_config.get('default_interval_seconds')
    if value is None:
        raise ValueError(f"default_interval_seconds missing in {config_path}")
    try:
        interval = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"default_interval_seconds must be a number in {config_path}") from exc
    if interval <= 0:
        raise ValueError(f"default_interval_seconds must be greater than 0 in {config_path}")
    return interval


def load_psk_map(path: str | Path) -> dict[str, str]:
    """加载 sensor_id 到 PSK 十六进制字符串的映射。

    Args:
        path: PSK JSON 配置文件路径。
    """
    raw = load_json(path)
    psk_map: dict[str, str] = {}
    for sensor_id, entry in raw.items():
        if not isinstance(entry, dict):
            raise ValueError(f"PSK entry for {sensor_id} must be an object")
        psk_id = entry.get('psk_id')
        psk_hex = entry.get('psk_hex')
        if psk_id != sensor_id:
            raise ValueError(f"PSK id mismatch for {sensor_id}")
        if not isinstance(psk_hex, str):
            raise ValueError(f"PSK hex missing for {sensor_id}")
        psk_map[sensor_id] = psk_hex
    return psk_map
