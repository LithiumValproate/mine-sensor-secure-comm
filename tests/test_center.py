# 这组测试覆盖中心端构建逻辑的配置校验行为。

from __future__ import annotations

from pathlib import Path

import pytest

from mine_sensor_secure_comm.center import build_core


def test_build_core_rejects_invalid_sensors_section(
        tmp_path: Path,
) -> None:
    """中心端构建逻辑应和其他入口一致地校验 sensors 段条目类型。"""
    sensor_config = tmp_path / 'sensors.toml'
    sensor_config.write_text(
        '[sensors]\n'
        'gas_sensor_01 = "invalid"\n'
        '\n'
        '[mqtt]\n'
        'host = "localhost"\n'
        'port = 8883\n'
        '\n'
        '[thresholds.gas]\n'
        'warning = 1.0\n'
        'critical = 1.5\n',
        encoding='utf-8',
    )
    psk_config = tmp_path / 'psk.json'
    psk_config.write_text('{}', encoding='utf-8')

    with pytest.raises(ValueError, match='invalid sensor entry'):
        build_core(
            str(sensor_config),
            str(psk_config),
        )
