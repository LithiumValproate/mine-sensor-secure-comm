"""Local security scenario runner."""

from __future__ import annotations

import argparse

from .center_core import GroundCenterCore
from .config_loader import load_psk_map
from .crypto_utils import encrypt_payload, new_boot_random
from .message import now_ms


def run_scenarios(psk_map: dict[str, str]) -> dict[str, str]:
    """Run replay, timestamp, identity, and decrypt-failure scenarios."""
    sensor_id = 'gas_sensor_01'
    core = GroundCenterCore(
        psk_map=psk_map,
        sensor_types={sensor_id: 'gas'},
        thresholds={'gas': {'warning': 1.0, 'critical': 1.5}},
    )
    boot_random = new_boot_random()
    timestamp_ms = now_ms()
    valid_payload = encrypt_payload(
        psk_hex=psk_map[sensor_id],
        sensor_id=sensor_id,
        sensor_type='gas',
        seq=1,
        timestamp_ms=timestamp_ms,
        plaintext={'value': 0.7, 'unit': '%LEL', 'battery': 99, 'location': 'mine-A-03', 'sample_time_ms': timestamp_ms},
        boot_random=boot_random,
    ).to_dict()

    results: dict[str, str] = {}
    results['valid'] = str(core.process_data_message(valid_payload, certificate_identity=sensor_id, receive_time_ms=timestamp_ms).accepted)
    replay = core.process_data_message(valid_payload, certificate_identity=sensor_id, receive_time_ms=timestamp_ms)
    results['replay'] = replay.alerts[0].code

    stale_payload = dict(valid_payload)
    stale_payload['seq'] = 2
    stale_payload['timestamp_ms'] = timestamp_ms - 301_000
    stale = core.process_data_message(stale_payload, certificate_identity=sensor_id, receive_time_ms=timestamp_ms)
    results['stale'] = stale.alerts[0].code

    forged = core.process_data_message(valid_payload, certificate_identity='temperature_sensor_01', receive_time_ms=timestamp_ms)
    results['forged_identity'] = forged.alerts[0].code

    tampered_payload = dict(valid_payload)
    tampered_payload['seq'] = 3
    tampered_payload['tag'] = 'AAAA'
    tampered = core.process_data_message(tampered_payload, certificate_identity=sensor_id, receive_time_ms=timestamp_ms)
    results['tampered'] = tampered.alerts[0].code
    return results


def main() -> None:
    """Run security scenarios against center core."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--psk-config', default='config/psk.json')
    args = parser.parse_args()
    print(run_scenarios(load_psk_map(args.psk_config)))


if __name__ == '__main__':
    main()
