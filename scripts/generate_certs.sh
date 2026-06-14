#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

mkdir -p "${PROJECT_DIR}/certs"

openssl genrsa -out "${PROJECT_DIR}/certs/ca.key" 4096
openssl req -x509 -new -nodes -key "${PROJECT_DIR}/certs/ca.key" -sha256 -days 3650 \
  -subj "/CN=mine-local-ca" \
  -out "${PROJECT_DIR}/certs/ca.crt"

create_cert() {
  local name="$1"
  local cn="$2"
  local san="$3"

  openssl genrsa -out "${PROJECT_DIR}/certs/${name}.key" 2048
  openssl req -new -key "${PROJECT_DIR}/certs/${name}.key" -subj "/CN=${cn}" -out "${PROJECT_DIR}/certs/${name}.csr"
  printf "subjectAltName=%s\nextendedKeyUsage=serverAuth,clientAuth\n" "$san" > "${PROJECT_DIR}/certs/${name}.ext"
  openssl x509 -req -in "${PROJECT_DIR}/certs/${name}.csr" -CA "${PROJECT_DIR}/certs/ca.crt" -CAkey "${PROJECT_DIR}/certs/ca.key" \
    -CAcreateserial -out "${PROJECT_DIR}/certs/${name}.crt" -days 825 -sha256 -extfile "${PROJECT_DIR}/certs/${name}.ext"
}

create_cert broker localhost "DNS:localhost,IP:127.0.0.1"
create_cert center center "DNS:center"
create_cert temperature_sensor_01 temperature_sensor_01 "DNS:temperature_sensor_01"
create_cert temperature_sensor_02 temperature_sensor_02 "DNS:temperature_sensor_02"
create_cert gas_sensor_01 gas_sensor_01 "DNS:gas_sensor_01"
create_cert gas_sensor_02 gas_sensor_02 "DNS:gas_sensor_02"

rm -f "${PROJECT_DIR}"/certs/*.csr "${PROJECT_DIR}"/certs/*.ext "${PROJECT_DIR}"/certs/ca.srl
chmod 600 "${PROJECT_DIR}"/certs/*.key
