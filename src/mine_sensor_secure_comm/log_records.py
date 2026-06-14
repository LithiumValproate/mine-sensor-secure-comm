"""Runtime log recording utilities."""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Any


class LogRecorder:
    """Keep recent logs in memory and optionally append them to a JSONL file."""

    def __init__(
            self,
            *,
            max_lines: int,
            log_path: Path | None = None,
    ) -> None:
        """Initialize a log recorder.

        Arg:
            max_lines: Maximum number of recent records kept for dashboard reads.
            log_path: Optional JSONL file used for persistent runtime records.
        """
        self.max_lines = max_lines
        self.log_path = log_path
        self.records: deque[dict[str, str]] = deque(maxlen=max_lines)
        if self.log_path is not None:
            self._load_recent_records()

    def append(self, source: str, line: str, *, ts: str | None = None) -> dict[str, str]:
        """Append one normalized log record."""
        record = {
            'ts': ts or time.strftime('%H:%M:%S'),
            'source': str(source),
            'line': line.rstrip(),
        }
        self.records.append(record)
        self._write_record(record)
        return record

    def snapshot(self) -> list[dict[str, str]]:
        """Return recent records in insertion order."""
        return list(self.records)

    def _load_recent_records(self) -> None:
        """Load valid recent JSONL records from the configured log path."""
        if self.log_path is None or not self.log_path.exists():
            return
        for raw_line in self.log_path.read_text(encoding='utf-8').splitlines():
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            record = self._normalize_record(payload)
            if record is not None:
                self.records.append(record)

    def _write_record(self, record: dict[str, str]) -> None:
        """Append a JSONL record when persistence is configured."""
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open('a', encoding='utf-8') as output:
            output.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _normalize_record(self, payload: Any) -> dict[str, str] | None:
        """Normalize one decoded JSONL value into the public log shape."""
        if not isinstance(payload, dict):
            return None
        if not all(key in payload for key in ('ts', 'source', 'line')):
            return None
        return {
            'ts': str(payload['ts']),
            'source': str(payload['source']),
            'line': str(payload['line']),
        }
