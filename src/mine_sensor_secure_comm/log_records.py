"""运行时日志记录工具。"""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Any


class LogRecorder:
    """在内存保留近期日志，并可追加写入 JSONL 文件。"""

    def __init__(
            self,
            *,
            max_lines: int,
            log_path: Path | None = None,
    ) -> None:
        """初始化日志记录器。

        Args:
            max_lines: 为控制台读取保留的近期记录数上限。
            log_path: 可选的 JSONL 文件路径，用于持久化运行时记录。
        """
        self.max_lines = max_lines
        self.log_path = log_path
        self.records: deque[dict[str, str]] = deque(maxlen=max_lines)
        if self.log_path is not None:
            self._load_recent_records()

    def append(self, source: str, line: str, *, ts: str | None = None) -> dict[str, str]:
        """追加一条标准化日志记录。"""
        record = {
            'ts': ts or time.strftime('%H:%M:%S'),
            'source': str(source),
            'line': line.rstrip(),
        }
        self.records.append(record)
        self._write_record(record)
        return record

    def snapshot(self) -> list[dict[str, str]]:
        """按插入顺序返回近期日志记录。"""
        return list(self.records)

    def _load_recent_records(self) -> None:
        """从配置的日志路径加载有效的近期 JSONL 记录。"""
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
        """在配置持久化路径时追加一条 JSONL 记录。"""
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open('a', encoding='utf-8') as output:
            output.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _normalize_record(self, payload: Any) -> dict[str, str] | None:
        """把解码后的 JSONL 值标准化为公开日志结构。"""
        if not isinstance(payload, dict):
            return None
        if not all(key in payload for key in ('ts', 'source', 'line')):
            return None
        return {
            'ts': str(payload['ts']),
            'source': str(payload['source']),
            'line': str(payload['line']),
        }
