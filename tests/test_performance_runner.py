from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'run_performance_tests.py'
SPEC = importlib.util.spec_from_file_location('run_performance_tests', MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_build_plot_series_match_report_shape() -> None:
    rows = [
        {'scenario': '无加密', 'sensor_count': '1', 'mean_latency_ms': '1.2', 'throughput_msg_s': '80.0'},
        {'scenario': '仅TLS', 'sensor_count': '1', 'mean_latency_ms': '2.3', 'throughput_msg_s': '75.0'},
        {'scenario': 'TLS+AES-GCM', 'sensor_count': '1', 'mean_latency_ms': '2.8', 'throughput_msg_s': '70.0'},
        {'scenario': 'TLS+AES-GCM', 'sensor_count': '2', 'mean_latency_ms': '3.0', 'throughput_msg_s': '130.0'},
        {'scenario': 'TLS+AES-GCM', 'sensor_count': '4', 'mean_latency_ms': '3.4', 'throughput_msg_s': '220.0'},
    ]

    latency_labels, latency_values = MODULE.build_latency_plot_series(rows)
    throughput_labels, throughput_values = MODULE.build_throughput_plot_series(rows)

    assert latency_labels == ['无加密', '仅TLS', 'TLS+AES-GCM']
    assert latency_values == [1.2, 2.3, 2.8]
    assert throughput_labels == ['1', '2', '4']
    assert throughput_values == [70.0, 130.0, 220.0]


def test_choose_sensor_ids_requires_enough_psk_entries() -> None:
    sensor_map = {
        'sensor_1': {},
        'sensor_2': {},
    }
    psk_map = {
        'sensor_1': '11' * 32,
    }

    with pytest.raises(ValueError, match='need at least 2 sensors'):
        MODULE.choose_sensor_ids(
            sensor_map=sensor_map,
            psk_map=psk_map,
            max_count=2,
        )


def test_plot_results_writes_png_files(tmp_path: Path) -> None:
    pytest.importorskip('matplotlib')

    csv_path = tmp_path / 'performance_results.csv'
    csv_path.write_text(
        '\n'.join([
            'test_id,scenario,scenario_key,sensor_count,messages_per_sensor,total_expected_messages,accepted_count,drop_count,decrypt_error_count,replay_error_count,mean_latency_ms,p50_ms,p95_ms,p99_ms,min_ms,max_ms,total_duration_s,throughput_msg_s',
            '1,无加密,no_encryption,1,1000,1000,1000,0,0,0,1.2,1.1,1.4,1.6,0.9,1.8,10.0,100.0',
            '2,仅TLS,tls_only,1,1000,1000,1000,0,0,0,2.3,2.2,2.5,2.7,2.0,2.9,11.0,90.0',
            '3,TLS+AES-GCM,tls_aes_gcm_latency,1,1000,1000,1000,0,0,0,2.8,2.7,3.0,3.2,2.3,3.5,12.0,83.3',
            '4,TLS+AES-GCM,tls_aes_gcm_throughput_2,2,1000,2000,2000,0,0,0,3.0,2.9,3.2,3.5,2.4,3.7,14.0,142.8',
            '5,TLS+AES-GCM,tls_aes_gcm_throughput_4,4,1000,4000,4000,0,0,0,3.4,3.2,3.6,3.9,2.8,4.1,18.0,222.2',
        ]),
        encoding='utf-8',
    )

    MODULE.plot_results(csv_path, tmp_path)

    assert (tmp_path / 'latency_by_encryption.png').exists()
    assert (tmp_path / 'throughput_by_sensor_count.png').exists()
