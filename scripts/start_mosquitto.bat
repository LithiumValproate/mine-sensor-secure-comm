@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"

if "%~1"=="" (
    if exist "%PROJECT_DIR%\config\mosquitto.conf" (
        set "CONFIG_PATH=%PROJECT_DIR%\config\mosquitto.conf"
    ) else (
        set "CONFIG_PATH=%PROJECT_DIR%\config\mosquitto.conf.example"
    )
) else (
    set "CONFIG_PATH=%~f1"
)

call :requireFile "%CONFIG_PATH%" "Mosquitto configuration" || exit /b 1
call :requireFile "%PROJECT_DIR%\certs\ca.crt" "CA certificate" || exit /b 1
call :requireFile "%PROJECT_DIR%\certs\broker.crt" "Broker certificate" || exit /b 1
call :requireFile "%PROJECT_DIR%\certs\broker.key" "Broker private key" || exit /b 1
call :findMosquitto || exit /b 1

echo Starting Mosquitto MQTT Broker...
echo Project directory: %PROJECT_DIR%
echo Config file: %CONFIG_PATH%
echo Mosquitto binary: %MOSQUITTO_BIN%
echo.

"%MOSQUITTO_BIN%" -c "%CONFIG_PATH%" -v
exit /b %errorlevel%

:requireFile
if not exist "%~1" (
    echo Missing %~2: %~1
    exit /b 1
)
exit /b 0

:findMosquitto
where mosquitto >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%I in ('where mosquitto') do (
        set "MOSQUITTO_BIN=%%~fI"
        exit /b 0
    )
)

for %%I in (
    "C:\Program Files\mosquitto\mosquitto.exe"
    "C:\Program Files (x86)\mosquitto\mosquitto.exe"
    "D:\Mosquitto\mosquitto.exe"
) do (
    if exist %%~I (
        set "MOSQUITTO_BIN=%%~fI"
        exit /b 0
    )
)

echo Mosquitto was not found.
echo Please install Mosquitto or add it to PATH.
exit /b 1
