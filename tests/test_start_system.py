# 这组测试覆盖启动器配置装配、运行时目录和状态映射逻辑。

from __future__ import annotations

import importlib.util
import random
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


def test_prepare_runtime_paths_creates_session_subdirectory(tmp_path: Path) -> None:
    """运行目录应位于日志根目录下的时间戳子目录中。"""
    session_name = MODULE.runtime_session_name(1718380800.0)
    runtime_dir, log_path = MODULE.prepare_runtime_paths(
        tmp_path / 'logs' / 'launcher.jsonl',
        1718380800.0,
    )

    assert runtime_dir == tmp_path / 'logs' / session_name
    assert log_path == runtime_dir / 'launcher.jsonl'


def test_initialize_runtime_workspace_copies_runtime_files(tmp_path: Path) -> None:
    """启动时应在本次运行目录中创建配置和日志目标。"""
    session_name = MODULE.runtime_session_name(1718380800.0)
    sensor_config_path = tmp_path / 'config' / 'sensors.toml'
    sensor_config_path.parent.mkdir(parents=True)
    sensor_config_path.write_text(
        '[simulation]\n'
        'default_interval_seconds = 0.5\n'
        'locations = ["采煤面"]\n'
        '\n'
        '[units]\n'
        'gas = "%CH4"\n'
        '\n'
        '[sensors.gas_sensor_01]\n'
        'type = "gas"\n'
        'unit = "%CH4"\n'
        'location = "采煤面"\n'
        'interval_seconds = 0.5\n'
        '\n'
        '[mqtt]\n'
        'host = "localhost"\n',
        encoding='utf-8',
    )
    psk_config_path = tmp_path / 'config' / 'psk.json'
    psk_config_path.write_text(
        '{"gas_sensor_01":{"psk_id":"gas_sensor_01","psk_hex":"' + '11' * 32 + '"}}',
        encoding='utf-8',
    )
    mosquitto_config_path = tmp_path / 'config' / 'mosquitto.conf'
    mosquitto_config_path.write_text('listener 8883\n', encoding='utf-8')

    runtime_dir, runtime_log_path, runtime_sensor_config_path, runtime_psk_config_path = (
        MODULE.initialize_runtime_workspace(
            sensor_config_path=sensor_config_path,
            psk_config_path=psk_config_path,
            mosquitto_config_path=mosquitto_config_path,
            log_path=tmp_path / 'logs' / 'launcher.jsonl',
            started_at=1718380800.0,
        )
    )

    assert runtime_dir == tmp_path / 'logs' / session_name
    assert runtime_log_path == runtime_dir / 'launcher.jsonl'
    assert runtime_sensor_config_path.read_text(encoding='utf-8')
    assert runtime_psk_config_path.read_text(encoding='utf-8')
    assert (runtime_dir / 'mosquitto.conf').read_text(encoding='utf-8') == 'listener 8883\n'


def test_build_runtime_sensor_spec_uses_config_defaults() -> None:
    """运行时传感器规格应使用配置中的默认值。"""
    spec = MODULE.build_runtime_sensor_spec(
        {
            'simulation': {
                'default_interval_seconds': 0.5,
                'locations': ['采煤面', '回风巷'],
            },
            'units': {'gas': '%CH4'},
            'thresholds': {'gas': {'warning': 1.0, 'critical': 1.5}},
        },
        ['gas_sensor_01', 'temperature_sensor_01'],
        psk_hex='aa' * 32,
        rng=random.Random(1),
    )

    assert spec.sensor_id == 'gas_sensor_02'
    assert spec.sensor_type == 'gas'
    assert spec.unit == '%CH4'
    assert spec.location in {'采煤面', '回风巷'}
    assert spec.interval_seconds == 0.5
    assert spec.thresholds == {'warning': 1.0, 'critical': 1.5}
    assert spec.catalog_entry()['sensor_id'] == 'gas_sensor_02'
    assert spec.psk_entry() == {
        'psk_id': 'gas_sensor_02',
        'psk_hex': 'aa' * 32,
    }


def test_build_runtime_sensor_spec_accepts_overrides() -> None:
    """运行时传感器规格应允许覆盖位置和采样间隔。"""
    spec = MODULE.build_runtime_sensor_spec(
        {
            'simulation': {
                'default_interval_seconds': 0.5,
                'locations': ['采煤面'],
            },
            'units': {'temperature': '°C'},
            'thresholds': {'temperature': {'warning': 45.0, 'critical': 60.0}},
        },
        ['temperature_sensor_01'],
        sensor_type='temperature',
        location='水泵房',
        interval_seconds=2.0,
        psk_hex='bb' * 32,
    )

    assert spec.sensor_id == 'temperature_sensor_02'
    assert spec.location == '水泵房'
    assert spec.interval_seconds == 2.0
    assert spec.unit == '°C'


def test_launcher_state_add_runtime_sensor_updates_runtime_config(tmp_path: Path) -> None:
    """启动器状态应接管运行时新增传感器配置。"""
    runtime_dir = tmp_path / 'runtime'
    sensor_config_path = runtime_dir / 'sensors.toml'
    psk_config_path = runtime_dir / 'psk.json'
    runtime_dir.mkdir(parents=True, exist_ok=True)
    state = MODULE.LauncherState(
        sensor_ids=['gas_sensor_01'],
        sensor_catalog={
            'gas_sensor_01': {
                'sensor_id': 'gas_sensor_01',
                'sensor_type': 'gas',
                'unit': '%CH4',
                'location': '采煤面',
                'interval_seconds': 0.5,
                'thresholds': {'warning': 1.0, 'critical': 1.5},
            },
        },
        sensor_config=str(sensor_config_path),
        psk_config=str(psk_config_path),
        mosquitto_config='config/mosquitto.conf',
        web_port=8000,
        runtime_psk_map={'gas_sensor_01': '11' * 32},
        sensor_config_data={
            'simulation': {
                'default_interval_seconds': 0.5,
                'locations': ['采煤面'],
            },
            'units': {'gas': '%CH4'},
            'sensors': {
                'gas_sensor_01': {
                    'type': 'gas',
                    'unit': '%CH4',
                    'location': '采煤面',
                    'interval_seconds': 0.5,
                },
            },
            'thresholds': {'gas': {'warning': 1.0, 'critical': 1.5}},
        },
    )
    spec = MODULE.RuntimeSensorSpec(
        sensor_id='gas_sensor_02',
        sensor_type='gas',
        unit='%CH4',
        location='回风巷',
        interval_seconds=0.5,
        psk_hex='22' * 32,
        thresholds={'warning': 1.0, 'critical': 1.5},
    )

    entry = state.add_runtime_sensor(spec)
    snapshot = state.snapshot()

    assert entry['sensor_id'] == 'gas_sensor_02'
    assert state.sensor_ids == ['gas_sensor_01', 'gas_sensor_02']
    assert state.runtime_psk_map['gas_sensor_02'] == '22' * 32
    assert state.runtime_sensor_specs['gas_sensor_02'] == spec
    assert snapshot['sensors'][1]['location'] == '回风巷'
    assert snapshot['logs'][-1]['line'] == 'registered runtime sensor gas_sensor_02'
    assert 'gas_sensor_02' in sensor_config_path.read_text(encoding='utf-8')
    assert 'gas_sensor_02' in psk_config_path.read_text(encoding='utf-8')


def test_launcher_state_rejects_duplicate_runtime_sensor() -> None:
    """启动器状态应拒绝重复注册的运行时传感器。"""
    state = MODULE.LauncherState(
        sensor_ids=['gas_sensor_01'],
        sensor_catalog={'gas_sensor_01': {'sensor_id': 'gas_sensor_01'}},
        sensor_config='config/sensors.toml',
        psk_config='config/psk.json',
        mosquitto_config='config/mosquitto.conf',
        web_port=8000,
    )
    spec = MODULE.RuntimeSensorSpec(
        sensor_id='gas_sensor_01',
        sensor_type='gas',
        unit='%CH4',
        location='回风巷',
        interval_seconds=0.5,
        psk_hex='22' * 32,
        thresholds={},
    )

    try:
        state.add_runtime_sensor(spec)
    except ValueError as exc:
        assert 'already exists' in str(exc)
    else:
        raise AssertionError('duplicate sensor should fail')


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
