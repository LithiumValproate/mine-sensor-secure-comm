# 这组测试覆盖基准测试入口对真实传感器配置的使用方式。

from __future__ import annotations

from mine_sensor_secure_comm.benchmark import run_local_crypto_benchmark


def test_run_local_crypto_benchmark_uses_selected_sensor_config() -> None:
    """基准测试应按指定传感器配置构造模拟器。"""
    sensor_config = {
        'sensors': {
            'temperature_sensor_01': {
                'type': 'temperature',
                'unit': '°C',
                'location': '回风巷',
                'interval_seconds': 1.0,
            },
        },
    }

    summary = run_local_crypto_benchmark(
        sensor_id='temperature_sensor_01',
        sensor_config=sensor_config,
        psk_hex='11' * 32,
        count=5,
    )

    assert summary['count'] == 5
    assert summary['drop_count'] == 0
    assert summary['decrypt_error_count'] == 0
    assert summary['replay_error_count'] == 0
