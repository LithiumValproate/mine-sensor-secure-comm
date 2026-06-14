from __future__ import annotations

import random
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
    config_path.write_text(
        '[simulation]\n'
        f'default_interval_seconds = {interval_seconds}\n'
        f'locations = [{quoted_locations}]\n'
        '\n'
        '[units]\n'
        'gas = "%CH4"\n'
        'temperature = "°C"\n',
        encoding='utf-8',
    )
    return config_path


def test_from_config_allocates_sensor_ids_in_creation_order(tmp_path: Path) -> None:
    """传感器 ID 应按进程内创建顺序分配。"""
    SensorNode._next_sequence = 1
    config_path = write_sensor_config(tmp_path)
    rng = random.Random(7)

    first = SensorNode.from_config(config_path, rng=rng)
    second = SensorNode.from_config(config_path, rng=rng)

    assert first.sensor_id == 'sensor_01'
    assert second.sensor_id == 'sensor_02'


def test_from_config_uses_random_location_and_default_interval(tmp_path: Path) -> None:
    """位置应来自 TOML，采样间隔应使用 TOML 默认值。"""
    SensorNode._next_sequence = 1
    locations = ['采煤工作面', '回风巷']
    config_path = write_sensor_config(
        tmp_path,
        locations=locations,
        interval_seconds=1.25,
    )

    node = SensorNode.from_config(config_path, rng=random.Random(3))

    assert node.location in locations
    assert node.sensor_type == 'gas'
    assert node.unit == '%CH4'
    assert node.interval_seconds == 1.25
    assert node.interval_sec == 1.25


def test_from_config_accepts_interval_override(tmp_path: Path) -> None:
    """显式传入的采样间隔应覆盖 TOML 默认值。"""
    SensorNode._next_sequence = 1
    config_path = write_sensor_config(tmp_path, interval_seconds=1.25)

    node = SensorNode.from_config(
        config_path,
        interval_sec=2.5,
        rng=random.Random(1),
    )

    assert node.interval_seconds == 2.5


def test_from_config_requires_locations(tmp_path: Path) -> None:
    """TOML 文件必须提供至少一个候选位置。"""
    config_path = write_sensor_config(tmp_path, locations=[])

    with pytest.raises(ValueError, match='simulation.locations'):
        SensorNode.from_config(config_path)


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
