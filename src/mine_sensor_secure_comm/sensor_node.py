"""MQTT sensor node publisher."""

from __future__ import annotations

import argparse
import json
import time

from .config_loader import load_psk_map, load_yaml
from .message import data_topic, encode_json, now_ms, status_topic
from .mqtt_runtime import make_tls_client
from .sensor_sim import SensorNodeSimulator, SensorProfile


def main() -> None:
    """Run one simulated sensor node."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--sensor-id', required=True)
    parser.add_argument('--sensor-config', default='config/sensors.yml')
    parser.add_argument('--psk-config', default='config/psk.json')
    parser.add_argument('--host', default=None)
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--count', type=int, default=0, help='0 means run forever')
    parser.add_argument('--plaintext', action='store_true', help='publish plaintext JSON for TLS-only benchmark')
    args = parser.parse_args()

    sensor_config = load_yaml(args.sensor_config)
    mqtt_config = sensor_config.get('mqtt', {})
    sensors = sensor_config.get('sensors', {})
    sensor = sensors[args.sensor_id]
    host = args.host or mqtt_config.get('host', 'localhost')
    port = args.port or int(mqtt_config.get('port', 8883))

    profile = SensorProfile(
        sensor_id=args.sensor_id,
        sensor_type=str(sensor['type']),
        unit=str(sensor['unit']),
        location=str(sensor['location']),
        interval_seconds=float(sensor.get('interval_seconds', 1.0)),
    )
    simulator = SensorNodeSimulator(profile, load_psk_map(args.psk_config)[args.sensor_id])
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
                    'sensor_type': profile.sensor_type,
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
            time.sleep(profile.interval_seconds)
    finally:
        client.publish(status_topic(args.sensor_id), encode_json({
            'sensor_id': args.sensor_id,
            'status': 'offline',
            'reason': 'normal_disconnect',
            'timestamp_ms': now_ms(),
        }), qos=1, retain=True)
        client.loop_stop()
        client.disconnect()


if __name__ == '__main__':
    main()
