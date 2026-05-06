"""Latency and crypto overhead benchmark helpers."""

from __future__ import annotations

import argparse
import statistics
import time
from typing import Any

from .crypto_utils import decrypt_payload
from .config_loader import load_psk_map
from .sensor_sim import SensorNodeSimulator, SensorProfile


def summarize_latencies(latencies_ns: list[int]) -> dict[str, Any]:
    """Return latency summary in milliseconds."""
    if not latencies_ns:
        return {'count': 0}
    values_ms = sorted(value / 1_000_000 for value in latencies_ns)
    return {
        'count': len(values_ms),
        'mean_ms': statistics.fmean(values_ms),
        'p50_ms': percentile(values_ms, 50),
        'p95_ms': percentile(values_ms, 95),
        'p99_ms': percentile(values_ms, 99),
        'min_ms': values_ms[0],
        'max_ms': values_ms[-1],
    }


def percentile(sorted_values: list[float], percent: int) -> float:
    """Return nearest-rank percentile."""
    index = max(0, min(len(sorted_values) - 1, round((percent / 100) * (len(sorted_values) - 1))))
    return sorted_values[index]


def run_local_crypto_benchmark(psk_hex: str, count: int) -> dict[str, Any]:
    """Measure local application-layer encrypt/decrypt overhead."""
    simulator = SensorNodeSimulator(
        SensorProfile('gas_sensor_01', 'gas', '%LEL', 'mine-A-03'),
        psk_hex,
    )
    latencies: list[int] = []
    drop_count = 0
    decrypt_error_count = 0
    for _ in range(count):
        start_ns = time.perf_counter_ns()
        payload = simulator.next_encrypted_payload().to_dict()
        try:
            decrypt_payload(psk_hex, payload)
        except Exception:
            decrypt_error_count += 1
            drop_count += 1
            continue
        latencies.append(time.perf_counter_ns() - start_ns)
    summary = summarize_latencies(latencies)
    summary.update({
        'drop_count': drop_count,
        'decrypt_error_count': decrypt_error_count,
        'replay_error_count': 0,
    })
    return summary


def main() -> None:
    """Run local application-layer crypto benchmark."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--psk-config', default='config/psk.json')
    parser.add_argument('--sensor-id', default='gas_sensor_01')
    parser.add_argument('--count', type=int, default=1000)
    args = parser.parse_args()
    psk_hex = load_psk_map(args.psk_config)[args.sensor_id]
    print(run_local_crypto_benchmark(psk_hex, args.count))


if __name__ == '__main__':
    main()
