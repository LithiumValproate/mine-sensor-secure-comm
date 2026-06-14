"""MQTT 传感器节点发布端。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from .config_loader import load_psk_map, load_sensor_config
from .message import data_topic, encode_json, now_ms, status_topic
from .mqtt_runtime import make_tls_client
from .sensor_node import SensorNode
from .sensor_sim import SensorNodeSimulator


def main() -> int:
    """运行一个模拟传感器节点。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--sensor-id', required=True)
    parser.add_argument('--sensor-config', default='config/sensors.toml')
    parser.add_argument('--psk-config', default='config/psk.json')
    parser.add_argument('--host', default=None)
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--count', type=int, default=0, help='0 means run forever')
    parser.add_argument('--plaintext', action='store_true', help='publish plaintext JSON for TLS-only benchmark')
    args = parser.parse_args()

    sensor_config = load_sensor_config(args.sensor_config)
    mqtt_config = sensor_config.get('mqtt', {})
    sensors = sensor_config.get('sensors', {})
    if not isinstance(sensors, dict):
        raise ValueError('invalid sensors section')
    sensor = _lookup_sensor_config(sensors, args.sensor_id)
    psk_map = load_psk_map(args.psk_config)
    psk_hex = _lookup_sensor_psk(psk_map, args.sensor_id)
    host = args.host or mqtt_config.get('host', 'localhost')
    port = args.port or int(mqtt_config.get('port', 8883))

    sensor_node = SensorNode(
        sensor_id=args.sensor_id,
        sensor_type=str(sensor['type']),
        unit=str(sensor['unit']),
        location=str(sensor['location']),
        interval_seconds=float(sensor.get('interval_seconds', 1.0)),
    )
    simulator = SensorNodeSimulator(sensor_node, psk_hex)
    client = make_tls_client(
        client_id=args.sensor_id,
        ca_file=mqtt_config.get('ca_file', 'certs/ca.crt'),
        cert_file=sensor.get('client_cert', f"certs/{args.sensor_id}.crt"),
        key_file=sensor.get('client_key', f"certs/{args.sensor_id}.key"),
    )

    offline_payload = encode_json({
        'sensor_id': args.sensor_id,
        'status': 'offline',
        'reason': 'unexpected_disconnect',
    })
    client.will_set(status_topic(args.sensor_id), offline_payload, qos=1, retain=True)
    client.connect(host, port, keepalive=60)
    client.loop_start()
    client.publish(status_topic(args.sensor_id), encode_json({
        'sensor_id': args.sensor_id,
        'status': 'online',
        'timestamp_ms': now_ms(),
    }), qos=1, retain=True)

    sent = 0
    try:
        while args.count == 0 or sent < args.count:
            if args.plaintext:
                payload = simulator.next_plain_reading()
                payload.update({
                    'version': 1,
                    'sensor_id': args.sensor_id,
                    'sensor_type': sensor_node.sensor_type,
                    'seq': simulator.seq,
                    'timestamp_ms': now_ms(),
                    'send_time_ns': time.perf_counter_ns(),
                })
                simulator.seq += 1
                mqtt_payload = encode_json(payload)
            else:
                encrypted = simulator.next_encrypted_payload().to_dict()
                encrypted['send_time_ns'] = time.perf_counter_ns()
                mqtt_payload = encode_json(encrypted)
            client.publish(data_topic(args.sensor_id), mqtt_payload, qos=1)
            print(json.dumps({'sensor_id': args.sensor_id, 'seq': simulator.seq - 1}, sort_keys=True))
            sent += 1
            time.sleep(sensor_node.interval_seconds)
    finally:
        client.publish(status_topic(args.sensor_id), encode_json({
            'sensor_id': args.sensor_id,
            'status': 'offline',
            'reason': 'normal_disconnect',
            'timestamp_ms': now_ms(),
        }), qos=1, retain=True)
        client.loop_stop()
        client.disconnect()
    return 0


def cli() -> int:
    """Run the CLI entrypoint with user-facing error handling."""
    try:
        return main()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _lookup_sensor_config(sensors: dict[str, Any], sensor_id: str) -> dict[str, Any]:
    """读取指定传感器配置，不存在时给出明确错误。"""
    sensor = sensors.get(sensor_id)
    if sensor is None:
        raise ValueError(f"sensor_id not found in sensor config: {sensor_id}")
    if not isinstance(sensor, dict):
        raise ValueError(f"invalid sensor entry for {sensor_id}")
    return sensor


def _lookup_sensor_psk(psk_map: dict[str, str], sensor_id: str) -> str:
    """读取指定传感器 PSK，不存在时给出明确错误。"""
    psk_hex = psk_map.get(sensor_id)
    if psk_hex is None:
        raise ValueError(f"sensor_id not found in PSK config: {sensor_id}")
    return psk_hex


if __name__ == '__main__':
    raise SystemExit(cli())
