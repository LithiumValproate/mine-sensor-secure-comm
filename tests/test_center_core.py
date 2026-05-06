from __future__ import annotations

from mine_sensor_secure_comm.center_core import GroundCenterCore
from mine_sensor_secure_comm.crypto_utils import encrypt_payload

PSK_HEX = '00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff'
BOOT_RANDOM = b'abcdefgh'


def make_core() -> GroundCenterCore:
    return GroundCenterCore(
        psk_map={'gas_sensor_01': PSK_HEX},
        sensor_types={'gas_sensor_01': 'gas'},
        thresholds={'gas': {'warning': 1.0, 'critical': 1.5}},
    )


def make_payload(seq: int, value: float = 0.5, timestamp_ms: int = 1_000_000) -> dict:
    return encrypt_payload(
        psk_hex=PSK_HEX,
        sensor_id='gas_sensor_01',
        sensor_type='gas',
        seq=seq,
        timestamp_ms=timestamp_ms,
        plaintext={
            'value': value,
            'unit': '%LEL',
            'battery': 90,
            'location': 'mine-A-03',
            'sample_time_ms': timestamp_ms,
        },
        boot_random=BOOT_RANDOM,
    ).to_dict()


def test_accepts_valid_payload() -> None:
    result = make_core().process_data_message(
        make_payload(seq=1),
        certificate_identity='gas_sensor_01',
        receive_time_ms=1_000_000,
    )

    assert result.accepted is True
    assert result.plaintext is not None
    assert result.alerts == []


def test_rejects_identity_mismatch() -> None:
    result = make_core().process_data_message(
        make_payload(seq=1),
        certificate_identity='temperature_sensor_01',
        receive_time_ms=1_000_000,
    )

    assert result.accepted is False
    assert result.alerts[0].code == 'identity_mismatch'


def test_detects_replay() -> None:
    core = make_core()
    payload = make_payload(seq=1)
    assert core.process_data_message(payload, certificate_identity='gas_sensor_01', receive_time_ms=1_000_000).accepted

    result = core.process_data_message(payload, certificate_identity='gas_sensor_01', receive_time_ms=1_000_000)

    assert result.accepted is False
    assert result.alerts[0].code == 'replay_detected'


def test_detects_timestamp_out_of_window() -> None:
    result = make_core().process_data_message(
        make_payload(seq=1, timestamp_ms=600_000),
        certificate_identity='gas_sensor_01',
        receive_time_ms=1_000_001,
    )

    assert result.accepted is False
    assert result.alerts[0].code == 'timestamp_out_of_window'


def test_generates_gas_threshold_alert() -> None:
    result = make_core().process_data_message(
        make_payload(seq=1, value=1.7),
        certificate_identity='gas_sensor_01',
        receive_time_ms=1_000_000,
    )

    assert result.accepted is True
    assert result.alerts[0].code == 'gas_threshold_exceeded'


def test_status_offline_alert() -> None:
    result = make_core().process_status_message({
        'sensor_id': 'gas_sensor_01',
        'status': 'offline',
        'reason': 'unexpected_disconnect',
    })

    assert result.accepted is True
    assert result.alerts[0].code == 'sensor_offline'
