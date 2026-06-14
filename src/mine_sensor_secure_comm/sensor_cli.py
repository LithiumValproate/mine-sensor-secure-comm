"""MQTT 传感器节点发布端。"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .config_loader import load_psk_map, load_sensor_config, load_sensor_entry
from .message import data_topic, encode_json, now_ms, status_topic
from .mqtt_runtime import make_tls_client
from .sensor_node import SensorNode
from .sensor_sim import SensorNodeSimulator


def main() -> int:
    """运行一个模拟传感器节点。

    默认发布经过 AES-GCM 加密的业务负载；传入 `--plaintext` 时改为
    发布仅受 TLS 保护的明文 JSON，便于做链路层性能对比。
    """
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
    sensor = load_sensor_entry(
        sensor_config,
        args.sensor_id,
        config_path=args.sensor_config,
    )
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
    """运行带用户态错误处理的 CLI 入口。"""
    try:
        return main()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _lookup_sensor_psk(psk_map: dict[str, str], sensor_id: str) -> str:
    """读取指定传感器 PSK，不存在时给出明确错误。

    Args:
        psk_map: 按传感器 ID 组织的 PSK 十六进制字符串映射。
        sensor_id: 要查找的传感器编号。
    """
    psk_hex = psk_map.get(sensor_id)
    if psk_hex is None:
        raise ValueError(f"sensor_id not found in PSK config: {sensor_id}")
    return psk_hex


if __name__ == '__main__':
    raise SystemExit(cli())
