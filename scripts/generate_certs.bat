@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "PYTHON_BIN=%PYTHON_BIN%"

if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_BIN=%PROJECT_DIR%\.venv\Scripts\python.exe"
)

if not defined PYTHON_BIN (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_BIN=py -3"
    ) else (
        set "PYTHON_BIN=python"
    )
)

if defined PYTHONPATH (
    set "PYTHONPATH=%PROJECT_DIR%\src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%PROJECT_DIR%\src"
)

call %PYTHON_BIN% -m mine_sensor_secure_comm.cert_cli %*
exit /b %errorlevel%
