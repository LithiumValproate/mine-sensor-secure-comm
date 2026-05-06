"""Shared MQTT client setup."""

from __future__ import annotations

import ssl

import paho.mqtt.client as mqtt


def make_tls_client(
    *,
    client_id: str,
    ca_file: str,
    cert_file: str,
    key_file: str,
) -> mqtt.Client:
    """Create a paho-mqtt client configured for mTLS."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.tls_set(
        ca_certs=ca_file,
        certfile=cert_file,
        keyfile=key_file,
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
    client.tls_insecure_set(False)
    return client


def certificate_common_name(client: mqtt.Client) -> str | None:
    """Best-effort extraction of peer certificate identity.

    Paho does not expose the client certificate subject from received publish
    callbacks. Mosquitto can map certificate CN to username, but the Python
    callback does not receive that username either. Runtime identity checks
    therefore use the payload identity unless an integration layer provides
    the certificate CN explicitly.
    """
    _ = client
    return None
