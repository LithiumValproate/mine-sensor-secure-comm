from __future__ import annotations

from mine_sensor_secure_comm.replay_guard import ReplayGuard


def test_accepts_fresh_sequence_once() -> None:
    guard = ReplayGuard(window_ms=300_000)

    assert guard.check('gas_sensor_01', 1, 1_000_000, 1_000_000) is None
    guard.accept('gas_sensor_01', 1, 1_000_000, 1_000_000)

    assert guard.check('gas_sensor_01', 1, 1_000_000, 1_000_000) == 'replay_detected'


def test_rejects_timestamp_out_of_window() -> None:
    guard = ReplayGuard(window_ms=300_000)

    assert guard.check('gas_sensor_01', 1, 600_000, 1_000_001) == 'timestamp_out_of_window'


def test_rejects_sequence_rollback() -> None:
    guard = ReplayGuard(window_ms=300_000)
    guard.accept('gas_sensor_01', 10, 1_000_000, 1_000_000)

    assert guard.check('gas_sensor_01', 9, 1_000_001, 1_000_001) == 'sequence_rollback'
