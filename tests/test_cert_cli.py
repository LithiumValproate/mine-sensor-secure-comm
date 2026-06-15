from __future__ import annotations

from pathlib import Path

import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID

from mine_sensor_secure_comm import cert_cli


def load_certificate(path: Path) -> x509.Certificate:
    """Load a PEM certificate for assertions."""
    return x509.load_pem_x509_certificate(path.read_bytes())


def test_parse_certificate_spec_supports_dns_and_ip_sans() -> None:
    """Certificate specs should preserve name, CN, and SAN entries."""
    spec = cert_cli.parse_certificate_spec('broker:localhost:DNS:localhost,IP:127.0.0.1')

    assert spec.name == 'broker'
    assert spec.common_name == 'localhost'
    assert spec.subject_alt_names == ('DNS:localhost', 'IP:127.0.0.1')


def test_generate_certificates_writes_ca_and_custom_cert(tmp_path: Path) -> None:
    """The generator should create PEM files with the requested names."""
    spec = cert_cli.parse_certificate_spec('edge_node:edge-node:DNS:edge-node')

    written_paths = cert_cli.generate_certificates(
        output_dir=tmp_path,
        ca_common_name='test-ca',
        specs=[spec],
        ca_key_bits=1024,
        key_bits=1024,
        ca_days=30,
        cert_days=10,
        force=False,
    )

    assert tmp_path / 'ca.key' in written_paths
    assert tmp_path / 'ca.crt' in written_paths
    assert tmp_path / 'edge_node.key' in written_paths
    assert tmp_path / 'edge_node.crt' in written_paths

    ca_certificate = load_certificate(tmp_path / 'ca.crt')
    leaf_certificate = load_certificate(tmp_path / 'edge_node.crt')
    ca_common_name = ca_certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    leaf_common_name = leaf_certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value

    assert ca_common_name == 'test-ca'
    assert leaf_common_name == 'edge-node'
    assert leaf_certificate.issuer == ca_certificate.subject


def test_generate_certificates_refuses_overwrite_without_force(tmp_path: Path) -> None:
    """Existing private keys should not be overwritten unless force is set."""
    (tmp_path / 'ca.key').write_text('existing', encoding='utf-8')
    spec = cert_cli.parse_certificate_spec('edge_node:edge-node:DNS:edge-node')

    with pytest.raises(FileExistsError, match='refusing to overwrite'):
        cert_cli.generate_certificates(
            output_dir=tmp_path,
            ca_common_name='test-ca',
            specs=[spec],
            ca_key_bits=1024,
            key_bits=1024,
            ca_days=30,
            cert_days=10,
            force=False,
        )


def test_cli_reports_invalid_san(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Unsupported SAN prefixes should fail with a clear error."""
    exit_code = cert_cli.cli([
        '--output-dir',
        str(tmp_path),
        '--only-custom',
        '--cert',
        'bad:bad:URI:bad',
        '--ca-key-bits',
        '1024',
        '--key-bits',
        '1024',
    ])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert 'unsupported SAN entry' in captured.err
    assert not (tmp_path / 'ca.key').exists()
