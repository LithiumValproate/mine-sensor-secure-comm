"""Replay detection for per-sensor sequence and timestamp windows."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SensorReplayState:
    """Replay state for one sensor."""

    last_seq: int = -1
    recent_seq: dict[int, int] = field(default_factory=dict)
    last_seen_ms: int = 0


class ReplayGuard:
    """Validate timestamp freshness and duplicate sequence numbers."""

    def __init__(self, window_ms: int = 300_000) -> None:
        self.window_ms = window_ms
        self._states: dict[str, SensorReplayState] = {}

    def check(self, sensor_id: str, seq: int, timestamp_ms: int, receive_time_ms: int) -> str | None:
        """Return an alert code when the message should be rejected."""
        if abs(receive_time_ms - timestamp_ms) > self.window_ms:
            return 'timestamp_out_of_window'

        state = self._states.setdefault(sensor_id, SensorReplayState())
        self._prune(state, receive_time_ms)

        if seq in state.recent_seq:
            return 'replay_detected'
        if seq <= state.last_seq:
            return 'sequence_rollback'
        return None

    def accept(self, sensor_id: str, seq: int, timestamp_ms: int, receive_time_ms: int) -> None:
        """Record an accepted message."""
        state = self._states.setdefault(sensor_id, SensorReplayState())
        state.last_seq = max(state.last_seq, seq)
        state.recent_seq[seq] = timestamp_ms
        state.last_seen_ms = receive_time_ms
        self._prune(state, receive_time_ms)

    def _prune(self, state: SensorReplayState, receive_time_ms: int) -> None:
        expired = [
            seq for seq, seen_ms in state.recent_seq.items()
            if receive_time_ms - seen_ms > self.window_ms
        ]
        for seq in expired:
            del state.recent_seq[seq]
