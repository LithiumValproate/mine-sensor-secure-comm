"""启动器辅助逻辑测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'start_system.py'
SPEC = importlib.util.spec_from_file_location('start_system', MODULE_PATH)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_select_mosquitto_config_falls_back_to_example(tmp_path: Path) -> None:
    """未提供正式配置时应回退到示例配置。"""
    (tmp_path / 'config').mkdir()
    example_path = tmp_path / 'config' / 'mosquitto.conf'
    example_path.write_text('listener 8883\n', encoding='utf-8')

    selected = MODULE.select_mosquitto_config(tmp_path, None)

    assert selected == example_path


def test_select_mosquitto_config_prefers_real_file(tmp_path: Path) -> None:
    """存在正式配置时应优先选择正式配置。"""
    (tmp_path / 'config').mkdir()
    real_path = tmp_path / 'config' / 'mosquitto.conf'
    real_path.write_text('listener 1883\n', encoding='utf-8')
    (tmp_path / 'config' / 'mosquitto.conf').write_text('listener 8883\n', encoding='utf-8')

    selected = MODULE.select_mosquitto_config(tmp_path, None)

    assert selected == real_path


def test_load_sensor_ids_reads_keys(tmp_path: Path) -> None:
    """传感器 ID 应按配置字典键读取。"""
    sensor_config = tmp_path / 'sensors.toml'
    sensor_config.write_text(
        '[sensors.gas_sensor_01]\n'
        'type = "gas"\n'
        '\n'
        '[sensors.temperature_sensor_01]\n'
        'type = "temperature"\n',
        encoding='utf-8',
    )

    sensor_ids = MODULE.load_sensor_ids(sensor_config)

    assert sensor_ids == ['gas_sensor_01', 'temperature_sensor_01']


def test_load_sensor_catalog_includes_thresholds(tmp_path: Path) -> None:
    """设备目录应包含前端实时监控需要的元数据。"""
    sensor_config = tmp_path / 'sensors.toml'
    sensor_config.write_text(
        '[sensors.gas_sensor_01]\n'
        'type = "gas"\n'
        'unit = "%LEL"\n'
        'location = "mine-A-03"\n'
        '\n'
        '[thresholds.gas]\n'
        'warning = 1.0\n'
        'critical = 1.5\n',
        encoding='utf-8',
    )

    catalog = MODULE.load_sensor_catalog(sensor_config)

    assert catalog['gas_sensor_01']['sensor_type'] == 'gas'
    assert catalog['gas_sensor_01']['unit'] == '%LEL'
    assert catalog['gas_sensor_01']['thresholds']['critical'] == 1.5


def test_select_config_with_example_uses_example_file(tmp_path: Path) -> None:
    """缺少正式配置时应自动回退到 .example。"""
    config_dir = tmp_path / 'config'
    config_dir.mkdir()
    example_path = config_dir / 'psk.json.example'
    example_path.write_text('{}', encoding='utf-8')

    selected = MODULE.select_config_with_example(tmp_path, 'config/psk.json', '.example')

    assert selected == example_path


def test_build_sensor_command_uses_sensor_cli() -> None:
    """启动器应调用真正的传感器 CLI 入口。"""
    command = MODULE.build_sensor_command(
        'gas_sensor_01',
        Path('config/sensors.toml'),
        Path('config/psk.json'),
        None,
        None,
    )

    assert 'mine_sensor_secure_comm.sensor_cli' in command
    assert 'config/sensors.toml' in command


def test_launcher_state_ingests_center_reading_and_alert() -> None:
    """中心端 JSON 日志应更新实时读数和通知历史。"""
    state = MODULE.LauncherState(
        sensor_ids=['gas_sensor_01'],
        sensor_catalog={
            'gas_sensor_01': {
                'sensor_id': 'gas_sensor_01',
                'sensor_type': 'gas',
                'unit': '%LEL',
                'location': 'mine-A-03',
                'thresholds': {'warning': 1.0, 'critical': 1.5},
            },
        },
        sensor_config='config/sensors.toml',
        psk_config='config/psk.json',
        mosquitto_config='config/mosquitto.conf',
        web_port=8000,
    )

    state.add_log('center', (
        '{"topic":"mine/gas_sensor_01/data","accepted":true,'
        '"plaintext":{"value":1.7,"unit":"%LEL","battery":88,'
        '"location":"mine-A-03","sample_time_ms":1000},'
        '"alerts":[{"code":"gas_threshold_exceeded","sensor_id":"gas_sensor_01",'
        '"severity":"high","message":"gas critical threshold exceeded",'
        '"details":{"value":1.7,"threshold":1.5}}]}'
    ))
    snapshot = state.snapshot()

    assert snapshot['sensors'][0]['value'] == 1.7
    assert snapshot['sensors'][0]['status'] == 'online'
    assert snapshot['alerts'][0]['code'] == 'gas_threshold_exceeded'


def test_launcher_state_builds_frontend_sensor_map() -> None:
    """兼容前端 API 应返回按传感器 ID 组织的数据。"""
    state = MODULE.LauncherState(
        sensor_ids=['temperature_sensor_01', 'gas_sensor_01'],
        sensor_catalog={
            'temperature_sensor_01': {
                'sensor_id': 'temperature_sensor_01',
                'sensor_type': 'temperature',
                'unit': '°C',
                'location': 'mine-A-01',
            },
            'gas_sensor_01': {
                'sensor_id': 'gas_sensor_01',
                'sensor_type': 'gas',
                'unit': '%LEL',
                'location': 'mine-A-03',
            },
        },
        sensor_config='config/sensors.toml',
        psk_config='config/psk.json',
        mosquitto_config='config/mosquitto.conf',
        web_port=8000,
    )

    state.add_log('center', (
        '{"topic":"mine/temperature_sensor_01/data","accepted":true,'
        '"plaintext":{"value":26.5,"unit":"°C","battery":91}}'
    ))
    state.add_log('center', (
        '{"topic":"mine/gas_sensor_01/data","accepted":true,'
        '"plaintext":{"value":0.8,"unit":"%LEL","battery":88}}'
    ))

    sensors = state.frontend_sensor_map()

    assert sensors['temperature_sensor_01']['last_temperature'] == 26.5
    assert sensors['temperature_sensor_01']['last_gas'] == '--'
    assert sensors['gas_sensor_01']['last_temperature'] == '--'
    assert sensors['gas_sensor_01']['last_gas'] == 0.8


def test_launcher_state_frontend_sensor_map_uses_placeholder_without_reading() -> None:
    """兼容前端 API 应在读数到达前使用占位值。"""
    state = MODULE.LauncherState(
        sensor_ids=['gas_sensor_01'],
        sensor_catalog={
            'gas_sensor_01': {
                'sensor_id': 'gas_sensor_01',
                'sensor_type': 'gas',
                'unit': '%LEL',
                'location': 'mine-A-03',
            },
        },
        sensor_config='config/sensors.toml',
        psk_config='config/psk.json',
        mosquitto_config='config/mosquitto.conf',
        web_port=8000,
    )

    sensors = state.frontend_sensor_map()

    assert sensors['gas_sensor_01']['last_temperature'] == '--'
    assert sensors['gas_sensor_01']['last_gas'] == '--'
