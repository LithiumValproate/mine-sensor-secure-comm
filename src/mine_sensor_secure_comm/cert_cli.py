"""本地测试证书生成命令。"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

DEFAULT_CERT_SPECS = (
    'broker:localhost:DNS:localhost,IP:127.0.0.1',
    'center:center:DNS:center',
    'temperature_sensor_01:temperature_sensor_01:DNS:temperature_sensor_01',
    'temperature_sensor_02:temperature_sensor_02:DNS:temperature_sensor_02',
    'gas_sensor_01:gas_sensor_01:DNS:gas_sensor_01',
    'gas_sensor_02:gas_sensor_02:DNS:gas_sensor_02',
)


@dataclass(frozen=True)
class CertificateSpec:
    """描述一个需要签发的叶子证书。

    Args:
        name: 证书和私钥文件名前缀。
        common_name: 证书 Common Name。
        subject_alt_names: Subject Alternative Name 字符串列表。
    """

    name: str
    common_name: str
    subject_alt_names: tuple[str, ...]


def parse_certificate_spec(raw_spec: str) -> CertificateSpec:
    """解析 `name:common_name:SAN[,SAN]` 形式的证书规格。

    Args:
        raw_spec: 命令行传入的证书规格字符串。
    """
    parts = raw_spec.split(':', 2)
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"invalid certificate spec: {raw_spec}")
    name, common_name, san_text = parts
    subject_alt_names = tuple(item.strip() for item in san_text.split(',') if item.strip())
    if not subject_alt_names:
        raise ValueError(f"certificate spec must include at least one SAN: {raw_spec}")
    return CertificateSpec(
        name=name,
        common_name=common_name,
        subject_alt_names=subject_alt_names,
    )


def build_subject_alt_name(entries: tuple[str, ...]) -> x509.SubjectAlternativeName:
    """根据命令行 SAN 字符串构造扩展字段。

    Args:
        entries: `DNS:name` 或 `IP:address` 形式的 SAN 列表。
    """
    san_entries: list[x509.GeneralName] = []
    for entry in entries:
        if entry.startswith('DNS:'):
            value = entry.removeprefix('DNS:')
            if not value:
                raise ValueError('DNS SAN must not be empty')
            san_entries.append(x509.DNSName(value))
        elif entry.startswith('IP:'):
            value = entry.removeprefix('IP:')
            if not value:
                raise ValueError('IP SAN must not be empty')
            san_entries.append(x509.IPAddress(ipaddress.ip_address(value)))
        else:
            raise ValueError(f"unsupported SAN entry: {entry}")
    return x509.SubjectAlternativeName(san_entries)


def build_name(common_name: str) -> x509.Name:
    """构造证书 subject/issuer name。

    Args:
        common_name: Common Name 字符串。
    """
    return x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])


def generate_private_key(key_bits: int) -> rsa.RSAPrivateKey:
    """生成 RSA 私钥。

    Args:
        key_bits: RSA 私钥长度。
    """
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_bits,
    )


def write_private_key(path: Path, private_key: rsa.RSAPrivateKey) -> None:
    """写入 PEM 私钥文件。

    Args:
        path: 输出路径。
        private_key: 要写入的 RSA 私钥。
    """
    path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    if os.name != 'nt':
        path.chmod(0o600)


def write_certificate(path: Path, certificate: x509.Certificate) -> None:
    """写入 PEM 证书文件。

    Args:
        path: 输出路径。
        certificate: 要写入的证书。
    """
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def ensure_can_write(paths: list[Path], *, force: bool) -> None:
    """确认输出文件不会被意外覆盖。

    Args:
        paths: 即将写入的路径列表。
        force: 是否允许覆盖已有文件。
    """
    existing_paths = [path for path in paths if path.exists()]
    if existing_paths and not force:
        joined = ', '.join(str(path) for path in existing_paths)
        raise FileExistsError(f"refusing to overwrite existing certificate files: {joined}")


def create_ca_certificate(
        *,
        common_name: str,
        key_bits: int,
        valid_days: int,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """生成自签 CA 证书。

    Args:
        common_name: CA Common Name。
        key_bits: CA 私钥长度。
        valid_days: CA 证书有效天数。
    """
    private_key = generate_private_key(key_bits)
    subject = build_name(common_name)
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=valid_days))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )
    return private_key, certificate


def create_leaf_certificate(
        *,
        spec: CertificateSpec,
        ca_private_key: rsa.RSAPrivateKey,
        ca_certificate: x509.Certificate,
        key_bits: int,
        valid_days: int,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """生成由本地 CA 签发的叶子证书。

    Args:
        spec: 叶子证书规格。
        ca_private_key: CA 私钥。
        ca_certificate: CA 证书。
        key_bits: 叶子证书私钥长度。
        valid_days: 叶子证书有效天数。
    """
    private_key = generate_private_key(key_bits)
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(build_name(spec.common_name))
        .issuer_name(ca_certificate.subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=valid_days))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            build_subject_alt_name(spec.subject_alt_names),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,
                ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .sign(ca_private_key, hashes.SHA256())
    )
    return private_key, certificate


def generate_certificates(
        *,
        output_dir: Path,
        ca_common_name: str,
        specs: list[CertificateSpec],
        ca_key_bits: int,
        key_bits: int,
        ca_days: int,
        cert_days: int,
        force: bool,
) -> list[Path]:
    """生成 CA、Broker、中心和传感器本地测试证书。

    Args:
        output_dir: 证书输出目录。
        ca_common_name: CA Common Name。
        specs: 叶子证书规格列表。
        ca_key_bits: CA 私钥长度。
        key_bits: 叶子证书私钥长度。
        ca_days: CA 证书有效天数。
        cert_days: 叶子证书有效天数。
        force: 是否允许覆盖已有文件。
    """
    for spec in specs:
        build_subject_alt_name(spec.subject_alt_names)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = [
        output_dir / 'ca.key',
        output_dir / 'ca.crt',
    ]
    for spec in specs:
        output_paths.extend([
            output_dir / f"{spec.name}.key",
            output_dir / f"{spec.name}.crt",
        ])
    ensure_can_write(output_paths, force=force)

    written_paths: list[Path] = []
    ca_private_key, ca_certificate = create_ca_certificate(
        common_name=ca_common_name,
        key_bits=ca_key_bits,
        valid_days=ca_days,
    )
    write_private_key(output_dir / 'ca.key', ca_private_key)
    write_certificate(output_dir / 'ca.crt', ca_certificate)
    written_paths.extend([
        output_dir / 'ca.key',
        output_dir / 'ca.crt',
    ])

    for spec in specs:
        private_key, certificate = create_leaf_certificate(
            spec=spec,
            ca_private_key=ca_private_key,
            ca_certificate=ca_certificate,
            key_bits=key_bits,
            valid_days=cert_days,
        )
        key_path = output_dir / f"{spec.name}.key"
        cert_path = output_dir / f"{spec.name}.crt"
        write_private_key(key_path, private_key)
        write_certificate(cert_path, certificate)
        written_paths.extend([key_path, cert_path])

    return written_paths


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description='Generate local test CA and mTLS certificates.',
    )
    parser.add_argument(
        '--output-dir',
        default='certs',
        help='证书输出目录，默认 certs',
    )
    parser.add_argument(
        '--ca-cn',
        default='mine-local-ca',
        help='CA 证书 Common Name，默认 mine-local-ca',
    )
    parser.add_argument(
        '--ca-days',
        type=int,
        default=3650,
        help='CA 证书有效天数，默认 3650',
    )
    parser.add_argument(
        '--cert-days',
        type=int,
        default=825,
        help='叶子证书有效天数，默认 825',
    )
    parser.add_argument(
        '--ca-key-bits',
        type=int,
        default=4096,
        help='CA RSA 私钥位数，默认 4096',
    )
    parser.add_argument(
        '--key-bits',
        type=int,
        default=2048,
        help='叶子证书 RSA 私钥位数，默认 2048',
    )
    parser.add_argument(
        '--cert',
        action='append',
        default=[],
        metavar='NAME:CN:SAN[,SAN]',
        help='追加一个证书规格，例如 broker:localhost:DNS:localhost,IP:127.0.0.1；可重复',
    )
    parser.add_argument(
        '--only-custom',
        action='store_true',
        help='只生成 --cert 指定的证书，不生成默认 broker/center/传感器证书',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='允许覆盖已有证书和私钥文件',
    )
    return parser


def cli(argv: list[str] | None = None) -> int:
    """运行证书生成命令。

    Args:
        argv: 命令行参数；为 None 时读取 `sys.argv`。
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.ca_days <= 0:
        parser.error('--ca-days must be greater than 0')
    if args.cert_days <= 0:
        parser.error('--cert-days must be greater than 0')
    if args.ca_key_bits < 1024:
        parser.error('--ca-key-bits must be at least 1024')
    if args.key_bits < 1024:
        parser.error('--key-bits must be at least 1024')

    raw_specs = []
    if not args.only_custom:
        raw_specs.extend(DEFAULT_CERT_SPECS)
    raw_specs.extend(args.cert)
    if not raw_specs:
        parser.error('at least one certificate spec is required')

    try:
        specs = [parse_certificate_spec(raw_spec) for raw_spec in raw_specs]
        written_paths = generate_certificates(
            output_dir=Path(args.output_dir),
            ca_common_name=args.ca_cn,
            specs=specs,
            ca_key_bits=args.ca_key_bits,
            key_bits=args.key_bits,
            ca_days=args.ca_days,
            cert_days=args.cert_days,
            force=args.force,
        )
    except (OSError, ValueError) as exc:
        print(f"mine-certs: {exc}", file=sys.stderr)
        return 1

    print(f"Generated {len(written_paths)} certificate files in {Path(args.output_dir)}")
    return 0


def main() -> None:
    """命令入口。"""
    raise SystemExit(cli())


if __name__ == '__main__':
    main()
