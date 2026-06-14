# Wireshark 抓包建议

这套系统的报告里，抓包不要只写“抓 `8883` 端口流量”，而是要能体现 **TLS 握手流程 + MQTT 业务数据传输流程**。

## 建议抓取的内容

### 1. Client Hello -> Server

这一段用于证明客户端发起了 TLS 握手。

建议在报告中体现：

- TLS 版本：`TLS 1.2`
- 协商的加密套件

可用过滤器：

```text
tcp.port == 8883
```

或：

```text
tls.handshake
```

### 2. Server Hello -> Client

这一段用于证明服务端响应握手，并向客户端发送证书链，同时要求客户端证书。

建议截图中包含：

- `Server Hello`
- `Certificate`
- `Certificate Request`

其中 `Certificate Request` 很关键，它能说明这里不是普通单向 TLS，而是 **双向认证 mTLS**。

### 3. Certificate -> Server

这一段用于体现客户端向服务端提交自己的证书。

建议在报告里说明：

- 客户端返回证书
- 服务端据此进行客户端身份校验

### 4. ClientKeyExchange / CertificateVerify / Finished

这一段用于体现握手的核心完成过程。

建议截图中包含：

- `ClientKeyExchange`
- `CertificateVerify`
- `Finished`

这一组包可以说明：

- 客户端完成密钥交换
- 客户端使用私钥完成签名证明
- 双方完成 TLS 握手

### 5. Application Data

这一段用于说明握手完成后，后续 MQTT 报文已经进入 TLS 加密通道。

建议在报告里说明：

- 握手完成后出现 `Application Data`
- 后续 MQTT 消息由 TLS 保护，抓包中无法直接看到明文业务内容

## 建议补充的业务流程抓包

如果你希望报告不仅体现握手，还体现“系统运行流程”，建议再补下面几类抓包。

### 6. 传感器上线

握手完成后，抓第一批业务报文，并结合程序日志说明这是传感器上线状态上报。

本项目中对应的 topic 是：

- `mine/<sensor_id>/status`

上线消息在代码里由传感器启动后发布，见 [src/mine_sensor_secure_comm/sensor_cli.py](/Users/kannazuki/Dev/mine-sensor-secure-comm/src/mine_sensor_secure_comm/sensor_cli.py:64)。

### 7. 传感器数据发布

继续抓几条后续业务报文，用来说明 TLS 通道中承载的是传感器数据上报。

本项目中对应的 topic 是：

- `mine/<sensor_id>/data`

数据发布逻辑见 [src/mine_sensor_secure_comm/sensor_cli.py](/Users/kannazuki/Dev/mine-sensor-secure-comm/src/mine_sensor_secure_comm/sensor_cli.py:89)。

### 8. 异常断开或正常下线

如果条件允许，建议再抓一段断开场景，用来说明 TLS 通道中还承载了状态变更通知。

本项目会发送：

- 正常下线：`status=offline`
- 异常断开：通过 MQTT Last Will 表示离线

相关逻辑见 [src/mine_sensor_secure_comm/sensor_cli.py](/Users/kannazuki/Dev/mine-sensor-secure-comm/src/mine_sensor_secure_comm/sensor_cli.py:56) 和 [src/mine_sensor_secure_comm/sensor_cli.py](/Users/kannazuki/Dev/mine-sensor-secure-comm/src/mine_sensor_secure_comm/sensor_cli.py:94)。

## 与本项目实现的对应关系

本仓库当前默认配置就是这条链路：

- Broker 监听 `8883`
- 使用 `TLS 1.2`
- 要求客户端证书

配置见 [config/mosquitto.conf](/Users/kannazuki/Dev/mine-sensor-secure-comm/config/mosquitto.conf:1)。

客户端侧也确实加载了 CA、客户端证书和私钥，见 [src/mine_sensor_secure_comm/mqtt_runtime.py](/Users/kannazuki/Dev/mine-sensor-secure-comm/src/mine_sensor_secure_comm/mqtt_runtime.py:10)。

地面中心连接后会订阅：

- `mine/+/data`
- `mine/+/status`

订阅逻辑见 [src/mine_sensor_secure_comm/center.py](/Users/kannazuki/Dev/mine-sensor-secure-comm/src/mine_sensor_secure_comm/center.py:71)。

## 推荐的抓包截图组合

如果是写实验报告，最实用的一组截图是：

1. `TLS 1.2 双向认证握手过程`
2. `Server Certificate Request 与客户端证书提交`
3. `握手完成后的 Application Data`
4. `传感器上线状态上报`
5. `传感器数据上报`
6. `正常下线或异常断开`

## 可直接写进报告的结论

可以在报告中这样概括：

> 抓包结果表明，系统首先在 `8883` 端口完成基于 `TLS 1.2` 的双向认证握手。服务端在握手阶段发送证书并请求客户端证书，客户端随后提交证书并完成密钥交换与签名验证。握手完成后，后续 MQTT 业务报文均以 `Application Data` 形式在 TLS 通道中传输，从而保证传感器状态与监测数据在网络中的机密性与完整性。

## 常用过滤器

```text
tcp.port == 8883
tls.handshake
tls
mqtt
```

## 补充说明

如果 Broker、地面中心、传感器都运行在本机，Wireshark 抓包时需要选对本地回环网卡，例如：

- `lo`
- `Loopback`

否则可能抓不到本机进程之间的通信。
