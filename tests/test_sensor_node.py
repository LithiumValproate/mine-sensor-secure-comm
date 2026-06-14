# 这组测试覆盖传感器节点配置读取和模拟器基本行为。

from __future__ import annotations

from pathlib import Path

import pytest

from mine_sensor_secure_comm.sensor_node import SensorNode
from mine_sensor_secure_comm.sensor_sim import SensorNodeSimulator


def write_sensor_config(
        tmp_path: Path,
        *,
        locations: list[str] | None = None,
        interval_seconds: float = 0.75,
) -> Path:
    """写入用于节点初始化测试的最小传感器 TOML 文件。"""
    config_path = tmp_path / 'sensors.toml'
    location_values = ['采煤工作面', '回风巷'] if locations is None else locations
    quoted_locations = ', '.join(f'"{location}"' for location in location_values)
    primary_location = location_values[0] if location_values else '采煤工作面'
    config_path.write_text(
        f'default_interval_seconds = {interval_seconds}\n'
        f'locations = [{quoted_locations}]\n'
        '\n'
        '[sensor_types.gas]\n'
        'unit = "%CH4"\n'
        '\n'
        '[sensor_types.temperature]\n'
        'unit = "°C"\n'
        '\n'
        '[sensors.gas_sensor_01]\n'
        'type = "gas"\n'
        'unit = "%CH4"\n'
        f'location = "{primary_location}"\n'
        f'interval_seconds = {interval_seconds}\n',
        encoding='utf-8',
    )
    return config_path


def test_from_config_reads_named_sensor_entry(tmp_path: Path) -> None:
    """传感器节点应按当前配置契约读取静态条目。"""
    config_path = write_sensor_config(tmp_path)

    node = SensorNode.from_config(
        config_path,
        sensor_id='gas_sensor_01',
    )

    assert node.sensor_id == 'gas_sensor_01'
    assert node.sensor_type == 'gas'
    assert node.unit == '%CH4'


def test_from_config_uses_sensor_entry_location_and_default_interval(tmp_path: Path) -> None:
    """静态配置节点应使用条目中的位置和采样间隔。"""
    locations = ['采煤工作面', '回风巷']
    config_path = write_sensor_config(
        tmp_path,
        locations=locations,
        interval_seconds=1.25,
    )

    node = SensorNode.from_config(
        config_path,
        sensor_id='gas_sensor_01',
    )

    assert node.location == '采煤工作面'
    assert node.sensor_type == 'gas'
    assert node.unit == '%CH4'
    assert node.interval_seconds == 1.25
    assert node.interval_sec == 1.25


def test_from_config_accepts_interval_override(tmp_path: Path) -> None:
    """显式传入的采样间隔应覆盖静态配置值。"""
    config_path = write_sensor_config(tmp_path, interval_seconds=1.25)

    node = SensorNode.from_config(
        config_path,
        sensor_id='gas_sensor_01',
        interval_sec=2.5,
    )

    assert node.interval_seconds == 2.5


def test_from_config_requires_sensor_id_or_sensor_type(tmp_path: Path) -> None:
    """未提供 sensor_id 时必须显式给出 sensor_type。"""
    config_path = write_sensor_config(tmp_path, locations=[])

    with pytest.raises(ValueError, match='sensor_type is required'):
        SensorNode.from_config(config_path)


def test_from_config_simulation_mode_requires_locations(tmp_path: Path) -> None:
    """模拟生成模式仍要求提供至少一个候选位置。"""
    config_path = write_sensor_config(tmp_path, locations=[])

    with pytest.raises(ValueError, match='locations'):
        SensorNode.from_config(
            config_path,
            sensor_type='gas',
        )


def test_sensor_node_simulator_uses_sensor_node_config() -> None:
    """模拟器应直接使用 SensorNode 中的静态配置。"""
    node = SensorNode(
        sensor_id='temperature_sensor_01',
        location='回风巷',
        sensor_type='temperature',
        unit='°C',
        interval_seconds=1.0,
    )

    simulator = SensorNodeSimulator(
        node,
        '00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff',
    )
    reading = simulator.next_plain_reading()
    encrypted = simulator.next_encrypted_payload().to_dict()

    assert reading['unit'] == '°C'
    assert reading['location'] == '回风巷'
    assert encrypted['sensor_id'] == 'temperature_sensor_01'
    assert encrypted['sensor_type'] == 'temperature'
