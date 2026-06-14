# 这组测试覆盖安全场景运行器对配置和结果码的联动。

from __future__ import annotations

from mine_sensor_secure_comm.security_tests import run_scenarios


def test_run_scenarios_uses_selected_sensor_config() -> None:
    """安全场景应使用传入的传感器配置，而不是固定 gas_sensor_01。"""
    sensor_config = {
        'sensor_types': {
            'temperature': {
                'unit': '°C',
                'warning_threshold': 45.0,
                'critical_threshold': 60.0,
            },
        },
        'sensors': {
            'temperature_sensor_01': {
                'type': 'temperature',
                'unit': '°C',
                'location': '回风巷',
                'interval_seconds': 1.0,
            },
        },
    }
    psk_map = {
        'temperature_sensor_01': '11' * 32,
    }

    results = run_scenarios(
        sensor_config=sensor_config,
        psk_map=psk_map,
        sensor_id='temperature_sensor_01',
    )

    assert results == {
        'valid': 'True',
        'replay': 'replay_detected',
        'stale': 'timestamp_out_of_window',
        'forged_identity': 'identity_mismatch',
        'tampered': 'decrypt_failed',
    }
