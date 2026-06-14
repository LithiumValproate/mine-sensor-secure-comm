# 这组测试覆盖运行时日志记录与 JSONL 持久化行为。

from __future__ import annotations

import json
from pathlib import Path

from mine_sensor_secure_comm.log_records import LogRecorder


def test_log_recorder_limits_snapshot_and_writes_jsonl(tmp_path: Path) -> None:
    """Log recorder should keep recent rows while persisting all appended rows."""
    log_path = tmp_path / 'logs' / 'launcher.jsonl'
    recorder = LogRecorder(max_lines=2, log_path=log_path)

    recorder.append('launcher', 'first\n', ts='12:00:00')
    recorder.append('center', 'second', ts='12:00:01')
    recorder.append('sensor', 'third', ts='12:00:02')

    assert recorder.snapshot() == [
        {'ts': '12:00:01', 'source': 'center', 'line': 'second'},
        {'ts': '12:00:02', 'source': 'sensor', 'line': 'third'},
    ]

    persisted = [
        json.loads(line)
        for line in log_path.read_text(encoding='utf-8').splitlines()
    ]
    assert persisted == [
        {'ts': '12:00:00', 'source': 'launcher', 'line': 'first'},
        {'ts': '12:00:01', 'source': 'center', 'line': 'second'},
        {'ts': '12:00:02', 'source': 'sensor', 'line': 'third'},
    ]


def test_log_recorder_loads_recent_valid_records(tmp_path: Path) -> None:
    """Existing JSONL logs should be loaded with invalid rows ignored."""
    log_path = tmp_path / 'launcher.jsonl'
    log_path.write_text(
        '{"ts":"12:00:00","source":"launcher","line":"old"}\n'
        'not-json\n'
        '{"source":"center","line":"missing timestamp"}\n'
        '{"ts":"12:00:01","source":"center","line":"new"}\n',
        encoding='utf-8',
    )

    recorder = LogRecorder(max_lines=1, log_path=log_path)

    assert recorder.snapshot() == [
        {'ts': '12:00:01', 'source': 'center', 'line': 'new'},
    ]
