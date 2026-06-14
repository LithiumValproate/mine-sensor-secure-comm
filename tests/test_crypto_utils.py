# 这组测试覆盖应用层加解密辅助函数的正确性与边界条件。

from __future__ import annotations

import pytest

from mine_sensor_secure_comm.crypto_utils import decrypt_payload, encrypt_payload

PSK_HEX = '00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff'
BOOT_RANDOM = b'12345678'


def test_encrypt_decrypt_round_trip() -> None:
    plaintext = {
        'value': 1.23,
        'unit': '%LEL',
        'battery': 87,
        'location': 'mine-A-03',
        'sample_time_ms': 1_714_989_600_000,
    }
    encrypted = encrypt_payload(
        psk_hex=PSK_HEX,
        sensor_id='gas_sensor_01',
        sensor_type='gas',
        seq=7,
        timestamp_ms=1_714_989_600_000,
        plaintext=plaintext,
        boot_random=BOOT_RANDOM,
    ).to_dict()

    assert decrypt_payload(PSK_HEX, encrypted) == plaintext


def test_aad_tampering_fails_decrypt() -> None:
    encrypted = encrypt_payload(
        psk_hex=PSK_HEX,
        sensor_id='gas_sensor_01',
        sensor_type='gas',
        seq=7,
        timestamp_ms=1_714_989_600_000,
        plaintext={'value': 1.23},
        boot_random=BOOT_RANDOM,
    ).to_dict()
    encrypted['sensor_type'] = 'temperature'

    with pytest.raises(Exception):
        decrypt_payload(PSK_HEX, encrypted)


def test_wrong_psk_fails_decrypt() -> None:
    encrypted = encrypt_payload(
        psk_hex=PSK_HEX,
        sensor_id='gas_sensor_01',
        sensor_type='gas',
        seq=7,
        timestamp_ms=1_714_989_600_000,
        plaintext={'value': 1.23},
        boot_random=BOOT_RANDOM,
    ).to_dict()

    with pytest.raises(Exception):
        decrypt_payload('ff' * 32, encrypted)
