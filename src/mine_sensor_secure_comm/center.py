"""Ground center MQTT subscriber."""

from __future__ import annotations

import argparse
import json

from .center_core import GroundCenterCore
from .config_loader import load_psk_map, load_yaml
from .message import decode_json, now_ms
from .mqtt_runtime import certificate_common_name, make_tls_client


def build_core(sensor_config_path: str, psk_config_path: str) -> GroundCenterCore:
    """Build center validation core from config files."""
    sensor_config = load_yaml(sensor_config_path)
    sensors = sensor_config.get('sensors', {})
    thresholds = sensor_config.get('thresholds', {})
    sensor_types = {
        sensor_id: str(config['type'])
        for sensor_id, config in sensors.items()
    }
    return GroundCenterCore(
        psk_map=load_psk_map(psk_config_path),
        sensor_types=sensor_types,
        thresholds=thresholds,
    )


def main() -> None:
    """Run ground center MQTT subscriber."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--sensor-config', default='config/sensors.yml')
    parser.add_argument('--psk-config', default='config/psk.json')
    parser.add_argument('--host', default=None)
    parser.add_argument('--port', type=int, default=None)
    args = parser.parse_args()

    sensor_config = load_yaml(args.sensor_config)
    mqtt_config = sensor_config.get('mqtt', {})
    host = args.host or mqtt_config.get('host', 'localhost')
    port = args.port or int(mqtt_config.get('port', 8883))
    core = build_core(args.sensor_config, args.psk_config)

    client = make_tls_client(
        client_id='ground_center',
        ca_file=mqtt_config.get('ca_file', 'certs/ca.crt'),
        cert_file=mqtt_config.get('center_cert', 'certs/center.crt'),
        key_file=mqtt_config.get('center_key', 'certs/center.key'),
    )

    def on_connect(client, userdata, flags, reason_code, properties):
        _ = userdata, flags, properties
        if reason_code != 0:
            print(f'center connect failed: {reason_code}')
            return
        client.subscribe('mine/+/data', qos=1)
        client.subscribe('mine/+/status', qos=1)
        print('ground center subscribed to mine/+/data and mine/+/status')

    def on_message(client, userdata, msg):
        _ = userdata
        try:
            payload = decode_json(msg.payload)
            if msg.topic.endswith('/status'):
                result = core.process_status_message(payload)
            else:
                result = core.process_data_message(
                    payload,
                    certificate_identity=certificate_common_name(client),
                    receive_time_ms=now_ms(),
                )
        except Exception as exc:
            print(json.dumps({'accepted': False, 'error': exc.__class__.__name__}, ensure_ascii=False))
            return

        print(json.dumps({
            'topic': msg.topic,
            'accepted': result.accepted,
            'plaintext': result.plaintext,
            'alerts': [alert.__dict__ for alert in result.alerts],
        }, ensure_ascii=False, sort_keys=True))

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=60)
    client.loop_forever()


if __name__ == '__main__':
    main()
