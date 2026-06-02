"""基于单传感器序列号和时间窗口的重放检测。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SensorReplayState:
    """单个传感器的重放检测状态。"""

    last_seq: int = -1
    recent_seq: dict[int, int] = field(default_factory=dict)
    last_seen_ms: int = 0


class ReplayGuard:
    """校验时间戳新鲜度和重复序列号。"""

    def __init__(self, window_ms: int = 300_000) -> None:
        """初始化重放防护器。

        Args:
            window_ms: 允许的时间戳偏差窗口，单位为毫秒。
        """
        self.window_ms = window_ms
        self._states: dict[str, SensorReplayState] = {}

    def check(self, sensor_id: str, seq: int, timestamp_ms: int, receive_time_ms: int) -> str | None:
        """在消息应被拒绝时返回告警代码。

        Args:
            sensor_id: 传感器编号。
            seq: 消息中的序列号。
            timestamp_ms: 消息自带的发送时间戳，单位为毫秒。
            receive_time_ms: 中心端接收消息的时间戳，单位为毫秒。
        """
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
        """记录一条已接受的消息。

        Args:
            sensor_id: 传感器编号。
            seq: 已接受消息的序列号。
            timestamp_ms: 已接受消息自带的时间戳，单位为毫秒。
            receive_time_ms: 中心端接收消息的时间戳，单位为毫秒。
        """
        state = self._states.setdefault(sensor_id, SensorReplayState())
        state.last_seq = max(state.last_seq, seq)
        state.recent_seq[seq] = timestamp_ms
        state.last_seen_ms = receive_time_ms
        self._prune(state, receive_time_ms)

    def _prune(self, state: SensorReplayState, receive_time_ms: int) -> None:
        """移除时间窗口外的历史序列号。

        Args:
            state: 单个传感器的重放检测状态。
            receive_time_ms: 当前接收时间戳，单位为毫秒。
        """
        expired = [
            seq for seq, seen_ms in state.recent_seq.items()
            if receive_time_ms - seen_ms > self.window_ms
        ]
        for seq in expired:
            del state.recent_seq[seq]
