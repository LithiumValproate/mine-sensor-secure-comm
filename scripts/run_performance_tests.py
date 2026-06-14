"""Run performance benchmarks and export report-ready charts."""

from __future__ import annotations

import argparse
import csv
import json
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / 'src'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import paho.mqtt.client as mqtt

from mine_sensor_secure_comm.benchmark import summarize_latencies
from mine_sensor_secure_comm.center import build_core
from mine_sensor_secure_comm.config_loader import (
    load_psk_map,
    load_sensor_config,
    load_sensor_entry,
    load_sensor_map,
)
from mine_sensor_secure_comm.message import data_topic, decode_json, encode_json, now_ms
from mine_sensor_secure_comm.mqtt_runtime import make_tls_client
from mine_sensor_secure_comm.sensor_node import SensorNode
from mine_sensor_secure_comm.sensor_sim import SensorNodeSimulator

DEFAULT_OUTPUT_DIR = PROJECT_DIR / 'outputs'
DEFAULT_TLS_PORT = 8883
DEFAULT_PLAIN_PORT = 1883
DEFAULT_MESSAGES_PER_SENSOR = 1000


@dataclass(frozen=True)
class ScenarioConfig:
    """Describe one benchmark scenario."""

    key: str
    label: str
    use_tls: bool
    use_payload_encryption: bool
    sensor_count: int
    messages_per_sensor: int
    broker_port: int
    publish_interval_seconds: float


@dataclass
class ScenarioResult:
    """Capture summary metrics for one scenario."""

    test_id: int
    scenario: str
    scenario_key: str
    sensor_count: int
    messages_per_sensor: int
    total_expected_messages: int
    accepted_count: int
    drop_count: int
    decrypt_error_count: int
    replay_error_count: int
    mean_latency_ms: float | None
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    min_ms: float | None
    max_ms: float | None
    total_duration_s: float | None
    throughput_msg_s: float | None

    def to_row(self) -> dict[str, Any]:
        """Return a CSV-serializable row."""
        return {
            'test_id': self.test_id,
            'scenario': self.scenario,
            'scenario_key': self.scenario_key,
            'sensor_count': self.sensor_count,
            'messages_per_sensor': self.messages_per_sensor,
            'total_expected_messages': self.total_expected_messages,
            'accepted_count': self.accepted_count,
            'drop_count': self.drop_count,
            'decrypt_error_count': self.decrypt_error_count,
            'replay_error_count': self.replay_error_count,
            'mean_latency_ms': self.mean_latency_ms,
            'p50_ms': self.p50_ms,
            'p95_ms': self.p95_ms,
            'p99_ms': self.p99_ms,
            'min_ms': self.min_ms,
            'max_ms': self.max_ms,
            'total_duration_s': self.total_duration_s,
            'throughput_msg_s': self.throughput_msg_s,
        }


class BenchmarkCollector:
    """Collect accepted messages and derive latency counters."""

    def __init__(
            self,
            *,
            expected_total: int,
            scenario: ScenarioConfig,
            sensor_config_path: Path,
            psk_config_path: Path,
    ) -> None:
        """Initialize a benchmark collector."""
        self.expected_total = expected_total
        self.scenario = scenario
        self.core = build_core(str(sensor_config_path), str(psk_config_path))
        sensor_config = load_sensor_config(sensor_config_path)
        self.sensor_map = load_sensor_map(
            sensor_config,
            config_path=sensor_config_path,
        )
        self._lock = threading.Lock()
        self._done = threading.Event()
        self.latencies_ns: list[int] = []
        self.accepted_count = 0
        self.processed_count = 0
        self.drop_count = 0
        self.decrypt_error_count = 0
        self.replay_error_count = 0
        self.end_perf_ns: int | None = None

    def on_message(self, client, userdata, msg) -> None:
        """Handle one incoming MQTT message."""
        _ = client, userdata
        receive_perf_ns = time.perf_counter_ns()
        try:
            payload = decode_json(msg.payload)
            if self.scenario.use_payload_encryption:
                result = self.core.process_data_message(
                    payload,
                    certificate_identity=None,
                    receive_time_ms=now_ms(),
                )
                send_time_ns = payload.get('send_time_ns')
            else:
                result = self._process_plaintext_payload(payload)
                send_time_ns = payload.get('send_time_ns')
        except Exception:
            with self._lock:
                self.drop_count += 1
                self.processed_count += 1
                self._maybe_finish_locked(receive_perf_ns)
            return

        with self._lock:
            self.processed_count += 1
            if result.accepted:
                self.accepted_count += 1
                latency_ns = _coerce_latency_ns(
                    send_time_ns=send_time_ns,
                    receive_perf_ns=receive_perf_ns,
                )
                if latency_ns is not None:
                    self.latencies_ns.append(latency_ns)
            else:
                self.drop_count += 1
                for alert in result.alerts:
                    if alert.code == 'decrypt_failed':
                        self.decrypt_error_count += 1
                    if alert.code in {'replay_detected', 'timestamp_out_of_window'}:
                        self.replay_error_count += 1
            self._maybe_finish_locked(receive_perf_ns)

    def wait(self, timeout_seconds: float) -> bool:
        """Wait until all expected messages are processed."""
        return self._done.wait(timeout_seconds)

    def summary(self, *, test_id: int, total_duration_s: float | None) -> ScenarioResult:
        """Build the final scenario summary."""
        latency_summary = summarize_latencies(self.latencies_ns)
        return ScenarioResult(
            test_id=test_id,
            scenario=self.scenario.label,
            scenario_key=self.scenario.key,
            sensor_count=self.scenario.sensor_count,
            messages_per_sensor=self.scenario.messages_per_sensor,
            total_expected_messages=self.expected_total,
            accepted_count=self.accepted_count,
            drop_count=self.drop_count,
            decrypt_error_count=self.decrypt_error_count,
            replay_error_count=self.replay_error_count,
            mean_latency_ms=latency_summary.get('mean_ms'),
            p50_ms=latency_summary.get('p50_ms'),
            p95_ms=latency_summary.get('p95_ms'),
            p99_ms=latency_summary.get('p99_ms'),
            min_ms=latency_summary.get('min_ms'),
            max_ms=latency_summary.get('max_ms'),
            total_duration_s=total_duration_s,
            throughput_msg_s=(
                self.accepted_count / total_duration_s
                if total_duration_s and total_duration_s > 0
                else None
            ),
        )

    def _process_plaintext_payload(self, payload: dict[str, Any]):
        """Reuse the same acceptance shape for plaintext payloads."""
        sensor_id = str(payload.get('sensor_id', ''))
        sensor_type = str(payload.get('sensor_type', ''))
        if sensor_id not in self.sensor_map:
            return _SimpleProcessResult(accepted=False, alert_codes=['unknown_sensor'])
        expected_type = str(self.sensor_map[sensor_id].get('type'))
        if sensor_type != expected_type:
            return _SimpleProcessResult(accepted=False, alert_codes=['identity_mismatch'])
        try:
            int(payload['seq'])
            int(payload['timestamp_ms'])
            int(payload['send_time_ns'])
        except (KeyError, TypeError, ValueError):
            return _SimpleProcessResult(accepted=False, alert_codes=['invalid_payload'])
        return _SimpleProcessResult(accepted=True, alert_codes=[])

    def _maybe_finish_locked(self, receive_perf_ns: int) -> None:
        """Mark the scenario complete once all messages were processed."""
        if self.processed_count >= self.expected_total and not self._done.is_set():
            self.end_perf_ns = receive_perf_ns
            self._done.set()


@dataclass(frozen=True)
class _SimpleAlert:
    """Represent a rejected plaintext message without importing extra types."""

    code: str


@dataclass
class _SimpleProcessResult:
    """Mirror the part of ProcessResult that the collector uses."""

    accepted: bool
    alert_codes: list[str]

    @property
    def alerts(self) -> list[_SimpleAlert]:
        """Expose alert-like objects with a code field."""
        return [_SimpleAlert(code=code) for code in self.alert_codes]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--sensor-config', default='config/sensors.toml')
    parser.add_argument('--psk-config', default='config/psk.json')
    parser.add_argument('--output-dir', default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument('--messages-per-sensor', type=int, default=DEFAULT_MESSAGES_PER_SENSOR)
    parser.add_argument('--sensor-counts', default='1,2,4')
    parser.add_argument('--latency-interval-seconds', type=float, default=0.01)
    parser.add_argument('--throughput-interval-seconds', type=float, default=0.0)
    parser.add_argument('--timeout-seconds', type=float, default=120.0)
    parser.add_argument('--plain-port', type=int, default=DEFAULT_PLAIN_PORT)
    parser.add_argument('--tls-port', type=int, default=DEFAULT_TLS_PORT)
    parser.add_argument('--plot-only', action='store_true')
    parser.add_argument('--results-csv', default=None)
    return parser.parse_args()


def main() -> int:
    """Run benchmarks and export charts."""
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_csv = Path(args.results_csv) if args.results_csv else output_dir / 'performance_results.csv'

    if args.plot_only:
        plot_results(results_csv, output_dir)
        print(json.dumps({
            'results_csv': str(results_csv),
            'latency_chart': str(output_dir / 'latency_by_encryption.png'),
            'throughput_chart': str(output_dir / 'throughput_by_sensor_count.png'),
        }, ensure_ascii=False, indent=2))
        return 0

    sensor_config_path = resolve_existing_path(args.sensor_config)
    psk_config_path = resolve_existing_path(args.psk_config, allow_example_fallback=True)
    sensor_config = load_sensor_config(sensor_config_path)
    sensor_map = load_sensor_map(
        sensor_config,
        config_path=sensor_config_path,
    )
    psk_map = load_psk_map(psk_config_path)
    sensor_ids = choose_sensor_ids(
        sensor_map=sensor_map,
        psk_map=psk_map,
        max_count=max(parse_sensor_counts(args.sensor_counts)),
    )
    tls_port = args.tls_port or int(sensor_config.get('mqtt', {}).get('port', DEFAULT_TLS_PORT))
    parsed_sensor_counts = parse_sensor_counts(args.sensor_counts)
    scenarios = build_scenarios(
        sensor_counts=parsed_sensor_counts,
        messages_per_sensor=args.messages_per_sensor,
        plain_port=args.plain_port,
        tls_port=tls_port,
        latency_interval_seconds=args.latency_interval_seconds,
        throughput_interval_seconds=args.throughput_interval_seconds,
    )

    results: list[ScenarioResult] = []
    for index, scenario in enumerate(scenarios, start=1):
        selected_sensor_ids = sensor_ids[: scenario.sensor_count]
        result = run_scenario(
            scenario=scenario,
            sensor_ids=selected_sensor_ids,
            sensor_config_path=sensor_config_path,
            psk_config_path=psk_config_path,
            test_id=index,
            timeout_seconds=args.timeout_seconds,
            output_dir=output_dir,
        )
        results.append(result)
        print(json.dumps(result.to_row(), ensure_ascii=False))

    write_results_csv(results_csv, results)
    write_summary_json(output_dir / 'performance_summary.json', results)
    plot_results(results_csv, output_dir)
    print(json.dumps({
        'results_csv': str(results_csv),
        'summary_json': str(output_dir / 'performance_summary.json'),
        'latency_chart': str(output_dir / 'latency_by_encryption.png'),
        'throughput_chart': str(output_dir / 'throughput_by_sensor_count.png'),
    }, ensure_ascii=False, indent=2))
    return 0


def parse_sensor_counts(value: str) -> tuple[int, ...]:
    """Parse a comma-separated sensor-count list."""
    counts = tuple(int(part.strip()) for part in value.split(',') if part.strip())
    if not counts:
        raise ValueError('sensor counts must not be empty')
    if any(count <= 0 for count in counts):
        raise ValueError('sensor counts must be positive integers')
    return counts


def resolve_existing_path(path_str: str, *, allow_example_fallback: bool = False) -> Path:
    """Resolve a configured file path within the project tree."""
    path = Path(path_str)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    if path.exists():
        return path
    if allow_example_fallback:
        example_path = path.with_suffix(path.suffix + '.example')
        if example_path.exists():
            return example_path
    raise FileNotFoundError(path)


def choose_sensor_ids(
        *,
        sensor_map: dict[str, dict[str, Any]],
        psk_map: dict[str, str],
        max_count: int,
) -> list[str]:
    """Select a stable sensor subset that has both config and PSK."""
    sensor_ids = [sensor_id for sensor_id in sensor_map if sensor_id in psk_map]
    if len(sensor_ids) < max_count:
        raise ValueError(
            f"need at least {max_count} sensors with matching PSK entries, found {len(sensor_ids)}",
        )
    return sensor_ids


def build_scenarios(
        *,
        sensor_counts: tuple[int, ...],
        messages_per_sensor: int,
        plain_port: int,
        tls_port: int,
        latency_interval_seconds: float,
        throughput_interval_seconds: float,
) -> list[ScenarioConfig]:
    """Build the five report scenarios."""
    throughput_counts = tuple(count for count in sensor_counts if count > 1)
    return [
        ScenarioConfig(
            key='no_encryption',
            label='无加密',
            use_tls=False,
            use_payload_encryption=False,
            sensor_count=1,
            messages_per_sensor=messages_per_sensor,
            broker_port=plain_port,
            publish_interval_seconds=latency_interval_seconds,
        ),
        ScenarioConfig(
            key='tls_only',
            label='仅TLS',
            use_tls=True,
            use_payload_encryption=False,
            sensor_count=1,
            messages_per_sensor=messages_per_sensor,
            broker_port=tls_port,
            publish_interval_seconds=latency_interval_seconds,
        ),
        ScenarioConfig(
            key='tls_aes_gcm_latency',
            label='TLS+AES-GCM',
            use_tls=True,
            use_payload_encryption=True,
            sensor_count=1,
            messages_per_sensor=messages_per_sensor,
            broker_port=tls_port,
            publish_interval_seconds=latency_interval_seconds,
        ),
        *[
            ScenarioConfig(
                key=f"tls_aes_gcm_throughput_{count}",
                label='TLS+AES-GCM',
                use_tls=True,
                use_payload_encryption=True,
                sensor_count=count,
                messages_per_sensor=messages_per_sensor,
                broker_port=tls_port,
                publish_interval_seconds=throughput_interval_seconds,
            )
            for count in throughput_counts
        ],
    ]


def run_scenario(
        *,
        scenario: ScenarioConfig,
        sensor_ids: list[str],
        sensor_config_path: Path,
        psk_config_path: Path,
        test_id: int,
        timeout_seconds: float,
        output_dir: Path,
) -> ScenarioResult:
    """Run one benchmark scenario end to end."""
    mosquitto_bin = find_mosquitto_executable()
    log_path = output_dir / f"{scenario.key}.log"
    broker_config_path = prepare_broker_config(
        scenario=scenario,
        output_dir=output_dir,
    )
    broker_process = start_broker(
        mosquitto_bin=mosquitto_bin,
        config_path=broker_config_path,
        log_path=log_path,
    )
    try:
        wait_for_port('127.0.0.1', scenario.broker_port, timeout_seconds=10.0)
        collector = BenchmarkCollector(
            expected_total=scenario.sensor_count * scenario.messages_per_sensor,
            scenario=scenario,
            sensor_config_path=sensor_config_path,
            psk_config_path=psk_config_path,
        )
        collector_client = build_subscriber_client(
            scenario=scenario,
            sensor_config_path=sensor_config_path,
        )
        connected = threading.Event()
        connection_error: list[int] = []

        def on_connect(client, userdata, flags, reason_code, properties) -> None:
            _ = userdata, flags, properties
            if reason_code == 0:
                client.subscribe('mine/+/data', qos=1)
                connected.set()
            else:
                connection_error.append(int(reason_code))
                connected.set()

        collector_client.on_connect = on_connect
        collector_client.on_message = collector.on_message
        collector_client.connect('127.0.0.1', scenario.broker_port, keepalive=60)
        collector_client.loop_start()
        try:
            if not connected.wait(10.0):
                raise TimeoutError(f"collector did not connect for scenario {scenario.key}")
            if connection_error:
                raise RuntimeError(f"collector connect failed: {connection_error[0]}")
            start_perf_ns = time.perf_counter_ns()
            publish_errors: list[BaseException] = []
            publish_error_lock = threading.Lock()

            def publish_one(sensor_id: str) -> None:
                try:
                    publish_sensor_messages(
                        scenario=scenario,
                        sensor_id=sensor_id,
                        sensor_config_path=sensor_config_path,
                        psk_config_path=psk_config_path,
                    )
                except BaseException as exc:  # noqa: BLE001
                    with publish_error_lock:
                        publish_errors.append(exc)

            publish_threads = [
                threading.Thread(
                    target=publish_one,
                    args=(sensor_id,),
                    daemon=True,
                )
                for sensor_id in sensor_ids
            ]
            for thread in publish_threads:
                thread.start()
            for thread in publish_threads:
                thread.join()
            if publish_errors:
                raise publish_errors[0]
            if not collector.wait(timeout_seconds):
                raise TimeoutError(f"scenario {scenario.key} timed out waiting for {collector.expected_total} messages")
            end_perf_ns = collector.end_perf_ns or time.perf_counter_ns()
        finally:
            collector_client.loop_stop()
            collector_client.disconnect()
    finally:
        stop_broker(broker_process)

    total_duration_s = (end_perf_ns - start_perf_ns) / 1_000_000_000
    return collector.summary(test_id=test_id, total_duration_s=total_duration_s)


def find_mosquitto_executable() -> str:
    """Locate a usable mosquitto binary."""
    candidates = [
        which('mosquitto'),
        '/opt/homebrew/sbin/mosquitto',
        '/opt/homebrew/bin/mosquitto',
        '/usr/local/sbin/mosquitto',
        '/usr/local/bin/mosquitto',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise FileNotFoundError('mosquitto')


def prepare_broker_config(*, scenario: ScenarioConfig, output_dir: Path) -> Path:
    """Return the config file path for the current scenario."""
    if scenario.use_tls:
        return PROJECT_DIR / 'config' / 'mosquitto.conf'
    plain_config_path = output_dir / 'mosquitto_plain.conf'
    plain_config_path.parent.mkdir(parents=True, exist_ok=True)
    plain_config_path.write_text(
        '\n'.join([
            f"listener {scenario.broker_port}",
            'protocol mqtt',
            'allow_anonymous true',
            'persistence false',
            'log_dest stdout',
            '',
        ]),
        encoding='utf-8',
    )
    return plain_config_path


def start_broker(*, mosquitto_bin: str, config_path: Path, log_path: Path) -> subprocess.Popen[str]:
    """Start a mosquitto broker process."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open('w', encoding='utf-8')
    return subprocess.Popen(
        [mosquitto_bin, '-c', str(config_path), '-v'],
        cwd=PROJECT_DIR,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_broker(process: subprocess.Popen[str]) -> None:
    """Stop the spawned mosquitto broker."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


def wait_for_port(host: str, port: int, *, timeout_seconds: float) -> None:
    """Wait until a TCP port starts accepting connections."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"port {host}:{port} did not become ready within {timeout_seconds} seconds")


def build_subscriber_client(*, scenario: ScenarioConfig, sensor_config_path: Path) -> mqtt.Client:
    """Build the subscriber client for one scenario."""
    if not scenario.use_tls:
        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"perf-center-{uuid.uuid4().hex[:8]}",
        )
    sensor_config = load_sensor_config(sensor_config_path)
    mqtt_config = sensor_config.get('mqtt', {})
    return make_tls_client(
        client_id=f"perf-center-{uuid.uuid4().hex[:8]}",
        ca_file=str(PROJECT_DIR / str(mqtt_config.get('ca_file', 'certs/ca.crt'))),
        cert_file=str(PROJECT_DIR / str(mqtt_config.get('center_cert', 'certs/center.crt'))),
        key_file=str(PROJECT_DIR / str(mqtt_config.get('center_key', 'certs/center.key'))),
    )


def build_publisher_client(
        *,
        scenario: ScenarioConfig,
        sensor_id: str,
        sensor_config_path: Path,
) -> mqtt.Client:
    """Build the publisher client for one sensor."""
    if not scenario.use_tls:
        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{sensor_id}-{uuid.uuid4().hex[:8]}",
        )
    sensor_config = load_sensor_config(sensor_config_path)
    mqtt_config = sensor_config.get('mqtt', {})
    sensor = load_sensor_entry(
        sensor_config,
        sensor_id,
        config_path=sensor_config_path,
    )
    return make_tls_client(
        client_id=f"{sensor_id}-{uuid.uuid4().hex[:8]}",
        ca_file=str(PROJECT_DIR / str(mqtt_config.get('ca_file', 'certs/ca.crt'))),
        cert_file=str(PROJECT_DIR / str(sensor.get('client_cert', f"certs/{sensor_id}.crt"))),
        key_file=str(PROJECT_DIR / str(sensor.get('client_key', f"certs/{sensor_id}.key"))),
    )


def publish_sensor_messages(
        *,
        scenario: ScenarioConfig,
        sensor_id: str,
        sensor_config_path: Path,
        psk_config_path: Path,
) -> None:
    """Publish one sensor's traffic for the given scenario."""
    sensor_config = load_sensor_config(sensor_config_path)
    sensor = load_sensor_entry(
        sensor_config,
        sensor_id,
        config_path=sensor_config_path,
    )
    psk_hex = load_psk_map(psk_config_path)[sensor_id]
    simulator = SensorNodeSimulator(
        SensorNode(
            sensor_id=sensor_id,
            sensor_type=str(sensor['type']),
            unit=str(sensor['unit']),
            location=str(sensor['location']),
            interval_seconds=float(sensor.get('interval_seconds', 0.5)),
        ),
        psk_hex,
    )
    client = build_publisher_client(
        scenario=scenario,
        sensor_id=sensor_id,
        sensor_config_path=sensor_config_path,
    )
    connected = threading.Event()
    connection_error: list[int] = []

    def on_connect(client, userdata, flags, reason_code, properties) -> None:
        _ = client, userdata, flags, properties
        if reason_code != 0:
            connection_error.append(int(reason_code))
        connected.set()

    client.on_connect = on_connect
    client.connect('127.0.0.1', scenario.broker_port, keepalive=60)
    client.loop_start()
    try:
        if not connected.wait(10.0):
            raise TimeoutError(f"publisher {sensor_id} did not connect")
        if connection_error:
            raise RuntimeError(f"publisher {sensor_id} connect failed: {connection_error[0]}")
        for _ in range(scenario.messages_per_sensor):
            payload = build_payload(
                scenario=scenario,
                sensor_id=sensor_id,
                sensor_type=str(sensor['type']),
                simulator=simulator,
            )
            info = client.publish(data_topic(sensor_id), encode_json(payload), qos=1)
            info.wait_for_publish()
            if scenario.publish_interval_seconds > 0:
                time.sleep(scenario.publish_interval_seconds)
    finally:
        client.loop_stop()
        client.disconnect()


def build_payload(
        *,
        scenario: ScenarioConfig,
        sensor_id: str,
        sensor_type: str,
        simulator: SensorNodeSimulator,
) -> dict[str, Any]:
    """Build one benchmark payload."""
    send_time_ns = time.perf_counter_ns()
    if scenario.use_payload_encryption:
        payload = simulator.next_encrypted_payload().to_dict()
        payload['send_time_ns'] = send_time_ns
        return payload
    payload = simulator.next_plain_reading()
    payload.update({
        'version': 1,
        'sensor_id': sensor_id,
        'sensor_type': sensor_type,
        'seq': simulator.seq,
        'timestamp_ms': now_ms(),
        'send_time_ns': send_time_ns,
    })
    simulator.seq += 1
    return payload


def _coerce_latency_ns(*, send_time_ns: Any, receive_perf_ns: int) -> int | None:
    """Return a non-negative latency if the payload carried a valid send timestamp."""
    try:
        send_ns = int(send_time_ns)
    except (TypeError, ValueError):
        return None
    return max(0, receive_perf_ns - send_ns)


def write_results_csv(path: Path, results: list[ScenarioResult]) -> None:
    """Write benchmark summaries to CSV."""
    fieldnames = list(results[0].to_row().keys()) if results else []
    with path.open('w', encoding='utf-8', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(result.to_row())


def write_summary_json(path: Path, results: list[ScenarioResult]) -> None:
    """Write benchmark summaries to JSON."""
    with path.open('w', encoding='utf-8') as json_file:
        json.dump([result.to_row() for result in results], json_file, ensure_ascii=False, indent=2)


def load_result_rows(path: Path) -> list[dict[str, str]]:
    """Load result rows from the CSV file."""
    with path.open('r', encoding='utf-8', newline='') as csv_file:
        return list(csv.DictReader(csv_file))


def build_latency_plot_series(rows: list[dict[str, str]]) -> tuple[list[str], list[float]]:
    """Return ordered latency bars for the report."""
    order = ['无加密', '仅TLS', 'TLS+AES-GCM']
    expected_keys = {
        'no_encryption',
        'tls_only',
        'tls_aes_gcm_latency',
    }
    latency_rows = [
        row for row in rows
        if row.get('scenario_key') in expected_keys
           or (
                   row.get('scenario') in order
                   and row.get('sensor_count') == '1'
           )
    ]
    value_by_label = {row['scenario']: float(row['mean_latency_ms']) for row in latency_rows if row['mean_latency_ms']}
    labels = [label for label in order if label in value_by_label]
    values = [value_by_label[label] for label in labels]
    return labels, values


def build_throughput_plot_series(rows: list[dict[str, str]]) -> tuple[list[str], list[float]]:
    """Return ordered throughput bars for the report."""
    throughput_rows = [
        row for row in rows
        if row.get('scenario_key') == 'tls_aes_gcm_latency'
           or str(row.get('scenario_key', '')).startswith('tls_aes_gcm_throughput_')
           or row.get('scenario') == 'TLS+AES-GCM'
    ]
    selected = sorted(
        {
            int(row['sensor_count']): float(row['throughput_msg_s'])
            for row in throughput_rows
            if row['throughput_msg_s']
        }.items(),
        key=lambda item: item[0],
    )
    labels = [str(sensor_count) for sensor_count, _ in selected]
    values = [throughput for _, throughput in selected]
    return labels, values


def plot_results(results_csv: Path, output_dir: Path) -> None:
    """Render both report charts from the result table."""
    import matplotlib

    matplotlib.use('Agg')
    matplotlib.rcParams['font.sans-serif'] = [
        'PingFang SC',
        'Hiragino Sans GB',
        'Microsoft YaHei',
        'Noto Sans CJK SC',
        'SimHei',
        'DejaVu Sans',
    ]
    matplotlib.rcParams['axes.unicode_minus'] = False
    from matplotlib import pyplot as plt

    rows = load_result_rows(results_csv)
    output_dir.mkdir(parents=True, exist_ok=True)

    latency_labels, latency_values = build_latency_plot_series(rows)
    throughput_labels, throughput_values = build_throughput_plot_series(rows)

    write_bar_chart(
        plt=plt,
        labels=latency_labels,
        values=latency_values,
        title='不同加密场景下的端到端延迟对比',
        x_label='加密场景',
        y_label='延迟 (毫秒)',
        output_path=output_dir / 'latency_by_encryption.png',
    )
    write_bar_chart(
        plt=plt,
        labels=throughput_labels,
        values=throughput_values,
        title='不同传感器数量下的吞吐量对比',
        x_label='传感器数量',
        y_label='吞吐量 (消息/秒)',
        output_path=output_dir / 'throughput_by_sensor_count.png',
    )


def write_bar_chart(
        *,
        plt,
        labels: list[str],
        values: list[float],
        title: str,
        x_label: str,
        y_label: str,
        output_path: Path,
) -> None:
    """Write one PNG bar chart."""
    if not labels or not values:
        raise ValueError(f"no chart data available for {title}")
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, values, color=['#355C7D', '#6C8EBF', '#3A7D44'][: len(labels)])
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    for bar, value in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{value:.3f}",
            ha='center',
            va='bottom',
        )
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


if __name__ == '__main__':
    raise SystemExit(main())
