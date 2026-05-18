#!/bin/zsh
set -euo pipefail

mkdir -p ../certs

openssl genrsa -out ../certs/ca.key 4096
openssl req -x509 -new -nodes -key ../certs/ca.key -sha256 -days 3650 \
  -subj "/CN=mine-local-ca" \
  -out ../certs/ca.crt

create_cert() {
  local name="$1"
  local cn="$2"
  local san="$3"

  openssl genrsa -out "../certs/${name}.key" 2048
  openssl req -new -key "../certs/${name}.key" -subj "/CN=${cn}" -out "../certs/${name}.csr"
  printf "subjectAltName=%s\nextendedKeyUsage=serverAuth,clientAuth\n" "$san" > "../certs/${name}.ext"
  openssl x509 -req -in "../certs/${name}.csr" -CA ../certs/ca.crt -CAkey ../certs/ca.key \
    -CAcreateserial -out "../certs/${name}.crt" -days 825 -sha256 -extfile "../certs/${name}.ext"
}

create_cert broker localhost "DNS:localhost,IP:127.0.0.1"
create_cert center center "DNS:center"
create_cert temperature_sensor_01 temperature_sensor_01 "DNS:temperature_sensor_01"
create_cert gas_sensor_01 gas_sensor_01 "DNS:gas_sensor_01"
create_cert gas_sensor_02 gas_sensor_02 "DNS:gas_sensor_02"

rm -f ../certs/*.csr ../certs/*.ext ../certs/ca.srl
chmod 600 ../certs/*.key
