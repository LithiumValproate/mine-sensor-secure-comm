# 这组测试覆盖传感器 CLI 在缺失配置时的失败路径。

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from mine_sensor_secure_comm import sensor_cli


def write_sensor_config(tmp_path: Path) -> Path:
    """Write a minimal sensor TOML config for CLI tests."""
    config_path = tmp_path / 'sensors.toml'
    config_path.write_text(
        '[sensors.gas_sensor_01]\n'
        'type = "gas"\n'
        'unit = "%CH4"\n'
        'location = "采煤面"\n'
        'interval_seconds = 0.5\n'
        '\n'
        '[mqtt]\n'
        'host = "localhost"\n'
        'port = 8883\n',
        encoding='utf-8',
    )
    return config_path


def write_psk_config(tmp_path: Path) -> Path:
    """Write a minimal PSK JSON config for CLI tests."""
    config_path = tmp_path / 'psk.json'
    config_path.write_text(
        json.dumps({
            'gas_sensor_01': {
                'psk_id': 'gas_sensor_01',
                'psk_hex': '11' * 32,
            },
        }),
        encoding='utf-8',
    )
    return config_path


def test_main_reports_missing_sensor_id_in_sensor_config(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI should fail cleanly when sensor_id is absent from sensors config."""
    sensor_config = write_sensor_config(tmp_path)
    psk_config = write_psk_config(tmp_path)
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'mine-sensor',
            '--sensor-id',
            'gas_sensor_99',
            '--sensor-config',
            str(sensor_config),
            '--psk-config',
            str(psk_config),
        ],
    )

    exit_code = sensor_cli.cli()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert 'sensor_id not found in sensor config: gas_sensor_99' in captured.err


def test_main_reports_missing_sensor_id_in_psk_config(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI should fail cleanly when sensor_id is absent from PSK config."""
    sensor_config = write_sensor_config(tmp_path)
    psk_config = tmp_path / 'psk.json'
    psk_config.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'mine-sensor',
            '--sensor-id',
            'gas_sensor_01',
            '--sensor-config',
            str(sensor_config),
            '--psk-config',
            str(psk_config),
        ],
    )

    exit_code = sensor_cli.cli()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert 'sensor_id not found in PSK config: gas_sensor_01' in captured.err
