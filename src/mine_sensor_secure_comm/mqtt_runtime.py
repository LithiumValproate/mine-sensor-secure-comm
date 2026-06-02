"""共享 MQTT 客户端配置。"""

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
    """创建已配置 mTLS 的 paho-mqtt 客户端。

    Args:
        client_id: MQTT 客户端编号。
        ca_file: CA 证书文件路径。
        cert_file: 客户端证书文件路径。
        key_file: 客户端私钥文件路径。
    """
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
    """尽力提取对端证书身份。

    Paho 不会在收到发布消息的回调中暴露客户端证书 subject。
    Mosquitto 可以把证书 CN 映射到 username，但 Python 回调同样拿不到
    这个 username。因此，除非集成层显式提供证书 CN，运行时身份检查会
    使用负载中的身份。

    Args:
        client: 当前 paho-mqtt 客户端实例。
    """
    _ = client
    return None
