from __future__ import annotations

from mine_sensor_secure_comm.benchmark import summarize_latencies


def test_summarize_latencies_reports_required_fields() -> None:
    summary = summarize_latencies([1_000_000, 2_000_000, 3_000_000])

    assert summary['count'] == 3
    assert summary['mean_ms'] == 2.0
    assert summary['p50_ms'] == 2.0
    assert summary['p95_ms'] == 3.0
    assert summary['p99_ms'] == 3.0
    assert summary['min_ms'] == 1.0
    assert summary['max_ms'] == 3.0
