"""延迟和加密开销基准测试辅助函数。"""

from __future__ import annotations

import argparse
import statistics
import time
from typing import Any

from .config_loader import load_psk_map, load_sensor_config, load_sensor_entry
from .crypto_utils import decrypt_payload
from .sensor_node import SensorNode
from .sensor_sim import SensorNodeSimulator


def summarize_latencies(latencies_ns: list[int]) -> dict[str, Any]:
    """返回以毫秒为单位的延迟统计。

    Args:
        latencies_ns: 以纳秒为单位记录的延迟列表。
    """
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
    """返回最近秩百分位数。

    Args:
        sorted_values: 已按升序排列的数值列表。
        percent: 要计算的百分位，例如 50、95 或 99。
    """
    index = max(0, min(len(sorted_values) - 1, round((percent / 100) * (len(sorted_values) - 1))))
    return sorted_values[index]


def run_local_crypto_benchmark(
        *,
        sensor_id: str,
        sensor_config: dict[str, Any],
        psk_hex: str,
        count: int,
) -> dict[str, Any]:
    """测量本地应用层加解密开销。

    Args:
        sensor_id: 参与测试的传感器编号。
        sensor_config: 已加载的传感器配置对象。
        psk_hex: 传感器 PSK 的十六进制字符串。
        count: 要执行的加解密轮数。
    """
    sensor = load_sensor_entry(sensor_config, sensor_id)
    simulator = SensorNodeSimulator(
        SensorNode(
            sensor_id=sensor_id,
            location=str(sensor['location']),
            sensor_type=str(sensor['type']),
            unit=str(sensor['unit']),
            interval_seconds=float(sensor.get('interval_seconds', 0.5)),
        ),
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
    """运行本地应用层加密基准测试。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--sensor-config', default='config/sensors.toml')
    parser.add_argument('--psk-config', default='config/psk.json')
    parser.add_argument('--sensor-id', default='gas_sensor_01')
    parser.add_argument('--count', type=int, default=1000)
    args = parser.parse_args()
    psk_hex = load_psk_map(args.psk_config)[args.sensor_id]
    sensor_config = load_sensor_config(args.sensor_config)
    print(run_local_crypto_benchmark(
        sensor_id=args.sensor_id,
        sensor_config=sensor_config,
        psk_hex=psk_hex,
        count=args.count,
    ))


if __name__ == '__main__':
    main()
