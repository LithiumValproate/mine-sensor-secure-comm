"""本地安全场景运行器。"""

from __future__ import annotations

import argparse

from .center_core import GroundCenterCore
from .config_loader import load_psk_map, load_sensor_config, load_sensor_entry
from .crypto_utils import encrypt_payload, new_boot_random
from .message import now_ms


def run_scenarios(
        *,
        sensor_config: dict[str, object | dict[str, object]],
        psk_map: dict[str, str],
        sensor_id: str = 'gas_sensor_01',
) -> dict[str, str]:
    """运行重放、时间戳、身份和解密失败场景。

    Args:
        sensor_config: 已加载的传感器配置对象。
        psk_map: 传感器编号到 PSK 十六进制字符串的映射。
        sensor_id: 参与测试的传感器编号。
    """
    sensor = load_sensor_entry(sensor_config, sensor_id)
    sensor_type = str(sensor['type'])
    core = GroundCenterCore(
        psk_map=psk_map,
        sensor_types={sensor_id: sensor_type},
        thresholds=sensor_config.get('thresholds', {}),
    )
    boot_random = new_boot_random()
    timestamp_ms = now_ms()
    valid_payload = encrypt_payload(
        psk_hex=psk_map[sensor_id],
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        seq=1,
        timestamp_ms=timestamp_ms,
        plaintext={
            'value': 0.7,
            'unit': str(sensor['unit']),
            'battery': 99,
            'location': str(sensor['location']),
            'sample_time_ms': timestamp_ms,
        },
        boot_random=boot_random,
    ).to_dict()

    results: dict[str, str] = {}
    results['valid'] = str(
        core.process_data_message(
            valid_payload,
            certificate_identity=sensor_id,
            receive_time_ms=timestamp_ms,
        ).accepted)
    replay = core.process_data_message(valid_payload, certificate_identity=sensor_id, receive_time_ms=timestamp_ms)
    results['replay'] = replay.alerts[0].code

    stale_payload = dict(valid_payload)
    stale_payload['seq'] = 2
    stale_payload['timestamp_ms'] = timestamp_ms - 301_000
    stale = core.process_data_message(stale_payload, certificate_identity=sensor_id, receive_time_ms=timestamp_ms)
    results['stale'] = stale.alerts[0].code

    forged_identity = 'temperature_sensor_01' if sensor_id != 'temperature_sensor_01' else 'gas_sensor_01'
    forged = core.process_data_message(
        valid_payload,
        certificate_identity=forged_identity,
        receive_time_ms=timestamp_ms,
    )
    results['forged_identity'] = forged.alerts[0].code

    tampered_payload = dict(valid_payload)
    tampered_payload['seq'] = 3
    tampered_payload['tag'] = 'AAAA'
    tampered = core.process_data_message(tampered_payload, certificate_identity=sensor_id, receive_time_ms=timestamp_ms)
    results['tampered'] = tampered.alerts[0].code
    return results


def main() -> None:
    """针对中心端核心运行安全场景。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--sensor-config', default='config/sensors.toml')
    parser.add_argument('--psk-config', default='config/psk.json')
    parser.add_argument('--sensor-id', default='gas_sensor_01')
    args = parser.parse_args()
    print(run_scenarios(
        sensor_config=load_sensor_config(args.sensor_config),
        psk_map=load_psk_map(args.psk_config),
        sensor_id=args.sensor_id,
    ))


if __name__ == '__main__':
    main()
