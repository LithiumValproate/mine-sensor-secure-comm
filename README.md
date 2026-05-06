# 基于 MQTT over TLS 的矿井传感安全通信系统

本仓库实现一个课程原型：多个 Python 传感器节点通过 Mosquitto Broker 使用 MQTT over mTLS 上报温度、瓦斯浓度等数据，地面中心完成身份验证、应用层解密、抗重放检测、异常告警和性能统计。

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

## 安全说明

- `config/psk.json`、`certs/` 中生成的私钥和证书均为本地测试材料，不应提交。
- 每个传感器使用独立 PSK，并通过 HKDF 派生 AES-128-GCM 密钥。
- AES-GCM nonce 使用 64 位启动随机数加 32 位序列号，避免同一密钥下重复。
