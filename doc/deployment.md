# 本地部署说明

本文档说明如何在 Windows、Linux 和 macOS 本地运行矿井传感安全通信系统。部署目标是启动一个 Mosquitto Broker、一个地面中心和一个或多个模拟传感器。

## 1. 环境准备

需要安装以下软件：

- 推荐 Python 3.12
- 支持 Python 3.10、3.11、3.12、3.13
- 不支持 Python 3.6
- 不建议使用 Python 3.14
- Mosquitto Broker
- OpenSSL

### 1.1 Windows

推荐方式：

1. 安装 Python 3.12，并勾选 “Add Python to PATH”。最低可使用 Python 3.10，不建议使用 3.14。
2. 安装 Mosquitto for Windows。
3. 安装 Git for Windows，用 Git Bash 运行本项目中的 Bash 脚本。
4. 确认 OpenSSL 可用。Git Bash 通常会附带 OpenSSL；也可以单独安装 OpenSSL for Windows。

在 PowerShell 中检查：

```powershell
python --version
pip --version
mosquitto -h
```

`python --version` 推荐输出 `Python 3.12.x`。如果输出 `Python 3.6.x` 或 `Python 3.14.x`，建议切换解释器后再安装项目依赖。

在 Git Bash 中检查：

```bash
openssl version
```

如果 `mosquitto` 不在 `PATH` 中，可以使用 Mosquitto 安装目录中的完整路径启动，例如：

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -h
```

证书生成脚本 `scripts/generate_certs.sh` 需要在 Git Bash 或 WSL 中运行。

### 1.2 Linux

Debian/Ubuntu：

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv mosquitto openssl
```

Fedora：

```bash
sudo dnf install -y python3 python3-pip mosquitto openssl
```

Arch Linux：

```bash
sudo pacman -S python python-pip mosquitto openssl
```

检查安装：

```bash
python3 --version
mosquitto -h
openssl version
```

如果系统默认 `python3` 不是 3.10 到 3.13，建议使用 `uv`、`pyenv` 或发行版提供的 Python 3.12 包创建项目环境。

### 1.3 macOS

使用 Homebrew：

```bash
brew install python@3.12 mosquitto openssl
```

检查安装：

```bash
python3.12 --version
mosquitto -h
openssl version
```

### 1.4 安装项目依赖

进入项目根目录后安装 Python 依赖：

```bash
python3 -m pip install -e '.[test]'
```

Windows PowerShell 中如果 `python3` 不可用，可以使用：

```powershell
python -m pip install -e ".[test]"
```

macOS 如果通过 Homebrew 安装了 `python@3.12`，也可以明确使用：

```bash
python3.12 -m pip install -e '.[test]'
```

如果小组使用 `uv` 管理环境，推荐统一为 Python 3.12：

```bash
uv python install 3.12
uv sync --python 3.12 --extra test
uv run pytest
```

## 2. 生成本地测试证书

在项目根目录运行：

```bash
./scripts/generate_certs.sh
```

Windows 下请在 Git Bash 或 WSL 中运行该命令。PowerShell 默认不能直接执行 `.sh` 脚本。

脚本会在 `certs/` 目录生成以下材料：

| 文件 | 作用 |
| --- | --- |
| `ca.crt` / `ca.key` | 本地测试 CA 证书和私钥 |
| `broker.crt` / `broker.key` | Mosquitto Broker 使用的服务端证书 |
| `center.crt` / `center.key` | 地面中心使用的客户端证书 |
| `temperature_sensor_01.crt` / `.key` | 温度传感器客户端证书 |
| `gas_sensor_01.crt` / `.key` | 瓦斯传感器 01 客户端证书 |
| `gas_sensor_02.crt` / `.key` | 瓦斯传感器 02 客户端证书 |

传感器证书的 CN 与 `sensor_id` 保持一致，例如 `gas_sensor_01`。这些证书只用于本地测试，不应作为生产证书使用。

## 3. 准备配置文件

复制示例配置：

```bash
cp config/psk.json.example config/psk.json
cp config/sensors.yml.example config/sensors.yml
```

Windows PowerShell：

```powershell
Copy-Item config\psk.json.example config\psk.json
Copy-Item config\sensors.yml.example config\sensors.yml
```

`config/sensors.yml` 包含三部分：

| 配置段 | 说明 |
| --- | --- |
| `sensors` | 传感器 ID、类型、单位、位置、上报间隔和客户端证书路径 |
| `thresholds` | 不同传感器类型的 warning 和 critical 阈值 |
| `mqtt` | Broker 地址、端口、CA 证书和地面中心证书路径 |

`config/psk.json` 保存每个传感器的 PSK：

```json
{
  "gas_sensor_01": {
    "psk_id": "gas_sensor_01",
    "psk_hex": "11112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
  }
}
```

`psk_id` 必须与外层 key 和传感器 ID 一致。`psk_hex` 是敏感信息，不应提交到版本库。

## 4. 启动 Mosquitto Broker

在项目根目录运行：

```bash
mosquitto -c config/mosquitto.conf.example
```

Windows PowerShell 如果 `mosquitto` 不在 `PATH` 中，可以运行：

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c config\mosquitto.conf.example
```

示例配置会监听 `8883` 端口，并启用 mTLS：

```conf
listener 8883
protocol mqtt

cafile certs/ca.crt
certfile certs/broker.crt
keyfile certs/broker.key

require_certificate true
use_identity_as_username true
allow_anonymous false
tls_version tlsv1.2
```

如果本地已有服务占用 `8883`，可以复制一份配置文件并修改端口，同时更新 `config/sensors.yml` 中的 `mqtt.port`。

## 5. 启动地面中心

打开新的终端窗口，在项目根目录运行：

```bash
mine-center --sensor-config config/sensors.yml --psk-config config/psk.json
```

Windows PowerShell：

```powershell
mine-center --sensor-config config\sensors.yml --psk-config config\psk.json
```

地面中心会订阅：

- `mine/+/data`
- `mine/+/status`

收到数据后，中心会输出 JSON 结果，包括是否接受、解密后的明文和告警列表。

## 6. 启动传感器

打开新的终端窗口运行：

```bash
mine-sensor --sensor-id gas_sensor_01 --sensor-config config/sensors.yml --psk-config config/psk.json
```

Windows PowerShell：

```powershell
mine-sensor --sensor-id gas_sensor_01 --sensor-config config\sensors.yml --psk-config config\psk.json
```

也可以启动其他传感器：

```bash
mine-sensor --sensor-id temperature_sensor_01 --sensor-config config/sensors.yml --psk-config config/psk.json
mine-sensor --sensor-id gas_sensor_02 --sensor-config config/sensors.yml --psk-config config/psk.json
```

Windows PowerShell：

```powershell
mine-sensor --sensor-id temperature_sensor_01 --sensor-config config\sensors.yml --psk-config config\psk.json
mine-sensor --sensor-id gas_sensor_02 --sensor-config config\sensors.yml --psk-config config\psk.json
```

默认情况下，传感器会持续上报。可以使用 `--count` 限制发送次数：

```bash
mine-sensor --sensor-id gas_sensor_01 --sensor-config config/sensors.yml --psk-config config/psk.json --count 10
```

Windows PowerShell：

```powershell
mine-sensor --sensor-id gas_sensor_01 --sensor-config config\sensors.yml --psk-config config\psk.json --count 10
```

## 7. 运行验证命令

离线单元测试：

```bash
pytest
```

本地加解密性能测试：

```bash
mine-bench --psk-config config/psk.json --count 1000
```

需要 Broker 的安全测试：

```bash
mine-sec-test --psk-config config/psk.json
```

Windows PowerShell 对应命令：

```powershell
pytest
mine-bench --psk-config config\psk.json --count 1000
mine-sec-test --psk-config config\psk.json
```

## 8. 关闭系统

推荐关闭顺序：

1. 停止传感器进程。
2. 停止地面中心进程。
3. 停止 Mosquitto Broker。

传感器异常断开时，Broker 会发布 Last Will 状态消息，地面中心应收到离线告警。

## 9. 排错

### 证书文件不存在

重新运行：

```bash
./scripts/generate_certs.sh
```

Windows 下在 Git Bash 或 WSL 中重新运行该脚本。并确认从项目根目录启动 Broker 和客户端。

### Windows 找不到 mine-center 或 mine-sensor

先确认项目已安装：

```powershell
python -m pip install -e ".[test]"
```

如果当前终端仍找不到命令，可以关闭并重新打开 PowerShell，或使用 Python 模块入口对应的控制台脚本目录。通常也可以直接在虚拟环境中运行这些命令。

### TLS 握手失败

检查以下内容：

- Broker 是否使用 `certs/broker.crt` 和 `certs/broker.key`。
- 客户端是否使用由 `certs/ca.crt` 对应 CA 签发的证书。
- `config/sensors.yml` 中的 `ca_file`、`center_cert`、`center_key`、`client_cert`、`client_key` 路径是否正确。

### 解密失败

检查以下内容：

- `config/psk.json` 中是否包含对应传感器 ID。
- `psk_id` 是否等于传感器 ID。
- 传感器端和地面中心是否使用同一份 PSK 配置。
- 消息外层字段是否被修改。

### 重放检测失败或序列号回退

同一传感器的 `seq` 必须递增。重复发布历史消息、复用旧 payload 或手动降低 `seq` 都会被拒绝。

### 阈值告警没有出现

检查 `config/sensors.yml` 中 `thresholds` 配置是否包含对应传感器类型，例如 `gas` 或 `temperature`。只有解密后的明文包含数值型 `value` 时，中心才会执行阈值检测。

## 10. 安全注意事项

- 不要提交 `config/psk.json`。
- 不要提交 `certs/*.key`。
- 不要在日志、截图或报告中暴露真实 PSK、私钥或生产证书。
- 本地脚本生成的证书只用于演示和测试。
- 如果迁移到生产环境，需要设计证书签发、证书吊销、密钥轮换和访问控制策略。
