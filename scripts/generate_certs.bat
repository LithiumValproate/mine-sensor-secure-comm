@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "CERT_DIR=%SCRIPT_DIR%..\certs"

where openssl >nul 2>nul  
if errorlevel 1 (
    echo OpenSSL was not found in PATH.
    echo Please install OpenSSL and try again.
    exit /b 1
)

if not exist "%CERT_DIR%" mkdir "%CERT_DIR%" || exit /b 1

openssl genrsa -out "%CERT_DIR%\ca.key" 4096 || exit /b 1
openssl req -x509 -new -nodes -key "%CERT_DIR%\ca.key" -sha256 -days 3650 -subj "/CN=mine-local-ca" -out "%CERT_DIR%\ca.crt" || exit /b 1

call :createCert broker localhost "DNS:localhost,IP:127.0.0.1" || exit /b 1
call :createCert center center "DNS:center" || exit /b 1
call :createCert temperature_sensor_01 temperature_sensor_01 "DNS:temperature_sensor_01" || exit /b 1
call :createCert gas_sensor_01 gas_sensor_01 "DNS:gas_sensor_01" || exit /b 1
call :createCert gas_sensor_02 gas_sensor_02 "DNS:gas_sensor_02" || exit /b 1

del /q "%CERT_DIR%\*.csr" "%CERT_DIR%\*.ext" "%CERT_DIR%\ca.srl" 2>nul

echo Local test certificates generated in "%CERT_DIR%".
exit /b 0

:createCert
set "CERT_NAME=%~1"
set "CERT_CN=%~2"
set "CERT_SAN=%~3"

openssl genrsa -out "%CERT_DIR%\%CERT_NAME%.key" 2048 || exit /b 1
openssl req -new -key "%CERT_DIR%\%CERT_NAME%.key" -subj "/CN=%CERT_CN%" -out "%CERT_DIR%\%CERT_NAME%.csr" || exit /b 1
(
    echo subjectAltName=%CERT_SAN%
    echo extendedKeyUsage=serverAuth,clientAuth
) > "%CERT_DIR%\%CERT_NAME%.ext"
openssl x509 -req -in "%CERT_DIR%\%CERT_NAME%.csr" -CA "%CERT_DIR%\ca.crt" -CAkey "%CERT_DIR%\ca.key" -CAcreateserial -out "%CERT_DIR%\%CERT_NAME%.crt" -days 825 -sha256 -extfile "%CERT_DIR%\%CERT_NAME%.ext" || exit /b 1
exit /b 0
