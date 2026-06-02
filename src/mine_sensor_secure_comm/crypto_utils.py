"""应用层 AES-GCM 加密辅助函数。"""

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
HKDF_INFO = b"mine-mqtt-payload-v1"
KEY_SIZE = 16
MAX_SEQ = 2 ** 32 - 1


@dataclass(frozen=True)
class EncryptedPayload:
    """序列化后的加密 MQTT 负载。"""

    version: int
    sensor_id: str
    sensor_type: str
    seq: int
    timestamp_ms: int
    nonce: str
    ciphertext: str
    tag: str

    def to_dict(self) -> dict[str, Any]:
        """返回可 JSON 序列化的表示形式。"""
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
    """以无填充形式编码字节，得到紧凑的 JSON 负载。

    Args:
        data: 要编码的原始字节。
    """
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode('ascii')


def b64url_decode(data: str) -> bytes:
    """解码无填充的 URL 安全 base64。

    Args:
        data: 无填充的 URL 安全 base64 字符串。
    """
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def canonical_json(data: dict[str, Any]) -> bytes:
    """以确定性形式编码 JSON，供加密和测试使用。

    Args:
        data: 要编码的 JSON 对象。
    """
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')


def derive_aes128_key(psk_hex: str, sensor_id: str) -> bytes:
    """使用 HKDF-SHA256 从 PSK 派生每个传感器独立的 AES-128 密钥。

    Args:
        psk_hex: PSK 的十六进制字符串。
        sensor_id: 传感器编号，用作 HKDF salt。
    """
    psk = bytes.fromhex(psk_hex)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=sensor_id.encode('utf-8'),
        info=HKDF_INFO,
    )
    return hkdf.derive(psk)


def build_aad(version: int, sensor_id: str, sensor_type: str, seq: int, timestamp_ms: int) -> bytes:
    """构建 AES-GCM 的附加认证数据。

    Args:
        version: 加密负载格式版本。
        sensor_id: 传感器编号。
        sensor_type: 传感器类型。
        seq: 消息序列号。
        timestamp_ms: 消息时间戳，单位为毫秒。
    """
    return canonical_json({
        'version': version,
        'sensor_id': sensor_id,
        'sensor_type': sensor_type,
        'seq': seq,
        'timestamp_ms': timestamp_ms,
    })


def make_nonce(boot_random: bytes, seq: int) -> bytes:
    """由启动随机数和 32 位序列号构建 96 位 GCM nonce。

    Args:
        boot_random: 进程启动时生成的 8 字节随机数。
        seq: 当前消息的 32 位序列号。
    """
    if len(boot_random) != 8:
        raise ValueError('boot_random must be exactly 8 bytes')
    if seq < 0 or seq > MAX_SEQ:
        raise ValueError('seq must fit in uint32')
    return boot_random + seq.to_bytes(4, 'big')


def new_boot_random() -> bytes:
    """生成进程级启动随机数，用于构造 nonce。"""
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
    """使用 AES-128-GCM 加密传感器读数。

    Args:
        psk_hex: PSK 的十六进制字符串。
        sensor_id: 传感器编号。
        sensor_type: 传感器类型。
        seq: 当前消息序列号。
        timestamp_ms: 当前消息时间戳，单位为毫秒。
        plaintext: 待加密的传感器明文读数。
        boot_random: 进程启动随机数，用于构造 nonce。
        version: 加密负载格式版本。
    """
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


def decrypt_payload(psk_hex: str, payload: EncryptedPayload | dict[str, Any]) -> dict[str, Any]:
    """解密并认证加密后的传感器负载。

    Args:
        psk_hex: PSK 的十六进制字符串。
        payload: 加密负载对象或其字典表示。
    """

    if isinstance(payload, EncryptedPayload):
        payload_dict = payload.to_dict()
    else:
        payload_dict = payload

    required = {'version', 'sensor_id', 'sensor_type', 'seq', 'timestamp_ms', 'nonce', 'ciphertext', 'tag'}
    missing = required.difference(payload_dict)
    if missing:
        raise ValueError(f"missing encrypted payload fields: {sorted(missing)}")

    version = int(payload_dict['version'])
    sensor_id = str(payload_dict['sensor_id'])
    sensor_type = str(payload_dict['sensor_type'])
    seq = int(payload_dict['seq'])
    timestamp_ms = int(payload_dict['timestamp_ms'])
    aad = build_aad(version, sensor_id, sensor_type, seq, timestamp_ms)
    key = derive_aes128_key(psk_hex, sensor_id)
    nonce = b64url_decode(str(payload_dict['nonce']))
    ciphertext = b64url_decode(str(payload_dict['ciphertext']))
    tag = b64url_decode(str(payload_dict['tag']))
    plaintext = AESGCM(key).decrypt(nonce, ciphertext + tag, aad)
    data = json.loads(plaintext.decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('decrypted payload must be a JSON object')
    return data
