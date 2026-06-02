#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

find_mosquitto() {
  if command -v mosquitto >/dev/null 2>&1; then
    command -v mosquitto
    return 0
  fi

  local candidate
  for candidate in \
    /opt/homebrew/sbin/mosquitto \
    /opt/homebrew/bin/mosquitto \
    /usr/local/sbin/mosquitto \
    /usr/local/bin/mosquitto; do
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  return 1
}

select_config() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$1"
  elif [[ -f "${PROJECT_DIR}/config/mosquitto.conf" ]]; then
    printf '%s\n' "${PROJECT_DIR}/config/mosquitto.conf"
  else
    printf '%s\n' "${PROJECT_DIR}/config/mosquitto.conf.example"
  fi
}

require_file() {
  local path="$1"
  local description="$2"

  if [[ ! -f "${path}" ]]; then
    printf '缺少%s: %s\n' "${description}" "${path}" >&2
    return 1
  fi
}

main() {
  local mosquitto_bin
  local config_path

  if ! mosquitto_bin="$(find_mosquitto)"; then
    cat >&2 <<'EOF'
未找到 mosquitto。
macOS 可用 Homebrew 安装：
  brew install mosquitto
EOF
    exit 1
  fi

  config_path="$(select_config "$@")"
  if [[ "${config_path}" != /* ]]; then
    config_path="${PROJECT_DIR}/${config_path}"
  fi

  require_file "${config_path}" 'Mosquitto 配置文件'
  require_file "${PROJECT_DIR}/certs/ca.crt" 'CA 证书'
  require_file "${PROJECT_DIR}/certs/broker.crt" 'Broker 证书'
  require_file "${PROJECT_DIR}/certs/broker.key" 'Broker 私钥'

  printf '正在启动 Mosquitto MQTT Broker...\n'
  printf '项目目录: %s\n' "${PROJECT_DIR}"
  printf '配置文件: %s\n' "${config_path}"
  printf 'Mosquitto: %s\n\n' "${mosquitto_bin}"

  cd "${PROJECT_DIR}"
  exec "${mosquitto_bin}" -c "${config_path}" -v
}

main "$@"
