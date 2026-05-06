"""Application-layer AES-GCM encryption helpers."""

from __future__ import annotations

import base64
import json
import secrets
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

GCM_NONCE_SIZE = 12
GCM_TAG_SIZE = 16
HKDF_INFO = b'mine-mqtt-payload-v1'
KEY_SIZE = 16
MAX_SEQ = 2 ** 32 - 1


@dataclass(frozen=True)
class EncryptedPayload:
    """Serialized encrypted MQTT payload."""

    version: int
    sensor_id: str
    sensor_type: str
    seq: int
    timestamp_ms: int
    nonce: str
    ciphertext: str
    tag: str

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable representation."""
        return {
            'version': self.version,
            'sensor_id': self.sensor_id,
            'sensor_type': self.sensor_type,
            'seq': self.seq,
            'timestamp_ms': self.timestamp_ms,
            'nonce': self.nonce,
            'ciphertext': self.ciphertext,
            'tag': self.tag,
        }


def b64url_encode(data: bytes) -> str:
    """Encode bytes without padding for compact JSON payloads."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def b64url_decode(data: str) -> bytes:
    """Decode unpadded URL-safe base64."""
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def canonical_json(data: dict[str, Any]) -> bytes:
    """Encode JSON in a deterministic form for encryption and tests."""
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')


def derive_aes128_key(psk_hex: str, sensor_id: str) -> bytes:
    """Derive a per-sensor AES-128 key from PSK using HKDF-SHA256."""
    psk = bytes.fromhex(psk_hex)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=sensor_id.encode('utf-8'),
        info=HKDF_INFO,
    )
    return hkdf.derive(psk)


def build_aad(version: int, sensor_id: str, sensor_type: str, seq: int, timestamp_ms: int) -> bytes:
    """Build authenticated additional data for AES-GCM."""
    return canonical_json({
        'version': version,
        'sensor_id': sensor_id,
        'sensor_type': sensor_type,
        'seq': seq,
        'timestamp_ms': timestamp_ms,
    })


def make_nonce(boot_random: bytes, seq: int) -> bytes:
    """Build a 96-bit GCM nonce from boot randomness and a 32-bit sequence."""
    if len(boot_random) != 8:
        raise ValueError('boot_random must be exactly 8 bytes')
    if seq < 0 or seq > MAX_SEQ:
        raise ValueError('seq must fit in uint32')
    return boot_random + seq.to_bytes(4, 'big')


def new_boot_random() -> bytes:
    """Generate per-process boot randomness for nonce construction."""
    return secrets.token_bytes(8)


def encrypt_payload(
        *,
        psk_hex: str,
        sensor_id: str,
        sensor_type: str,
        seq: int,
        timestamp_ms: int,
        plaintext: dict[str, Any],
        boot_random: bytes,
        version: int = 1,
) -> EncryptedPayload:
    """Encrypt a sensor reading with AES-128-GCM."""
    key = derive_aes128_key(psk_hex, sensor_id)
    nonce = make_nonce(boot_random, seq)
    aad = build_aad(version, sensor_id, sensor_type, seq, timestamp_ms)
    encrypted = AESGCM(key).encrypt(nonce, canonical_json(plaintext), aad)
    ciphertext = encrypted[:-GCM_TAG_SIZE]
    tag = encrypted[-GCM_TAG_SIZE:]
    return EncryptedPayload(
        version=version,
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        seq=seq,
        timestamp_ms=timestamp_ms,
        nonce=b64url_encode(nonce),
        ciphertext=b64url_encode(ciphertext),
        tag=b64url_encode(tag),
    )


def decrypt_payload(psk_hex: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Decrypt and authenticate an encrypted sensor payload."""
    required = {'version', 'sensor_id', 'sensor_type', 'seq', 'timestamp_ms', 'nonce', 'ciphertext', 'tag'}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f'missing encrypted payload fields: {sorted(missing)}')

    version = int(payload['version'])
    sensor_id = str(payload['sensor_id'])
    sensor_type = str(payload['sensor_type'])
    seq = int(payload['seq'])
    timestamp_ms = int(payload['timestamp_ms'])
    aad = build_aad(version, sensor_id, sensor_type, seq, timestamp_ms)
    key = derive_aes128_key(psk_hex, sensor_id)
    nonce = b64url_decode(str(payload['nonce']))
    ciphertext = b64url_decode(str(payload['ciphertext']))
    tag = b64url_decode(str(payload['tag']))
    plaintext = AESGCM(key).decrypt(nonce, ciphertext + tag, aad)
    data = json.loads(plaintext.decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('decrypted payload must be a JSON object')
    return data
