# 基于 MQTT over TLS 的矿井传感安全通信系统

本仓库实现一个课程原型：多个 Python 传感器节点通过 Mosquitto Broker 使用 MQTT over mTLS 上报温度、瓦斯浓度等数据，地面中心完成身份验证、应用层解密、抗重放检测、异常告警和性能统计。

## 项目目标

本项目用于演示矿井传感器在不可信网络中的安全上报流程。系统同时使用传输层 mTLS 和应用层 AES-GCM 加密，验证以下能力：

- 传感器与地面中心通过 Mosquitto Broker 完成 MQTT 通信。
- Broker 使用 mTLS 验证客户端证书，客户端验证 Broker 证书。
- 传感器数据在应用层使用每节点 PSK 派生出的 AES-128-GCM 密钥加密。
- 地面中心检测消息篡改、错误密钥、重复序列号、时间戳超窗和阈值异常。
- 传感器异常断开时通过 MQTT Last Will 发布离线状态。

## 环境要求

- 推荐 Python 3.12。
- 支持 Python 3.10、3.11、3.12、3.13。
- 不支持 Python 3.6；代码和依赖使用了 Python 3.10+ 特性。
- 不建议使用 Python 3.14；项目元数据限制为 `>=3.10,<3.14`，避免依赖兼容性风险。
- Mosquitto Broker，需支持 TLS。
- OpenSSL，用于生成本地测试证书。

Windows、Linux 和 macOS 的完整本地部署说明见 [doc/deployment.md](doc/deployment.md)。

## 快速开始

1. 安装依赖：

   ```bash
   python3 -m pip install -e '.[test]'
   ```

2. 生成本地测试证书：

   ```bash
   ./scripts/generate_certs.sh
   ```

3. 复制示例配置：

   ```bash
   cp config/psk.json.example config/psk.json
   cp config/sensors.yml.example config/sensors.yml
   ```

4. 启动 Mosquitto：

   ```bash
   mosquitto -c config/mosquitto.conf.example
   ```

5. 启动地面中心：

   ```bash
   mine-center --sensor-config config/sensors.yml --psk-config config/psk.json
   ```

6. 启动传感器：

   ```bash
   mine-sensor --sensor-id gas_sensor_01 --sensor-config config/sensors.yml --psk-config config/psk.json
   ```

也可以启动其他示例传感器：

```bash
mine-sensor --sensor-id temperature_sensor_01 --sensor-config config/sensors.yml --psk-config config/psk.json
mine-sensor --sensor-id gas_sensor_02 --sensor-config config/sensors.yml --psk-config config/psk.json
```

## 使用 uv

如果小组统一使用 `uv`，推荐锁定 Python 3.12：

```bash
uv python install 3.12
uv sync --python 3.12 --extra test
uv run pytest
```

已有 `.venv` 不能原地切换 Python 主版本。需要切换时，删除旧环境后重建：

```bash
rm -rf .venv
uv venv --python 3.12
uv sync --extra test
```

## 测试

离线单元测试不需要真实 MQTT Broker：

```bash
pytest
```

安全测试和性能测试需要先启动 Mosquitto：

```bash
mine-sec-test --psk-config config/psk.json
mine-bench --psk-config config/psk.json --count 1000
```

## 配置文件

| 文件 | 说明 |
| --- | --- |
| `config/sensors.yml` | 传感器列表、类型、单位、位置、上报间隔、证书路径和阈值 |
| `config/psk.json` | 传感器 ID 到 PSK 的映射，属于敏感配置 |
| `config/mosquitto.conf.example` | Mosquitto mTLS 示例配置 |
| `certs/` | 本地测试 CA、Broker、中心和传感器证书 |

仓库只提交 `.example` 示例配置。实际运行时需要复制并按环境修改，不应提交真实密钥或私钥。

## 安全说明

- `config/psk.json`、`certs/` 中生成的私钥和证书均为本地测试材料，不应提交。
- 每个传感器使用独立 PSK，并通过 HKDF 派生 AES-128-GCM 密钥。
- AES-GCM nonce 使用 64 位启动随机数加 32 位序列号，避免同一密钥下重复。
- 外层消息中的 `sensor_id`、`sensor_type`、`seq` 和 `timestamp_ms` 会作为 AES-GCM AAD 参与认证，篡改后解密应失败。
- 地面中心默认使用 5 分钟时间窗口检测过期或超前消息。

## 常见问题

### Broker 启动失败

检查 `certs/ca.crt`、`certs/broker.crt`、`certs/broker.key` 是否已生成，并确认当前目录是项目根目录。

### 客户端连接被拒绝

确认已运行 `./scripts/generate_certs.sh`，并检查 `config/sensors.yml` 中的证书路径是否存在。mTLS 模式下，传感器和地面中心都必须使用由同一 CA 签发的客户端证书。

### 地面中心解密失败

检查 `config/psk.json` 中对应 `sensor_id` 的 `psk_hex` 是否与传感器端一致。错误 PSK、篡改过的外层字段或损坏的密文都会导致解密失败。

### 收到重放或序列号回退告警

这是抗重放逻辑的预期行为。同一传感器的 `seq` 必须递增，重复发布历史消息会被拒绝。
