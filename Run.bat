@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "PYTHON_BIN=%PYTHON_BIN%"

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_BIN=%SCRIPT_DIR%.venv\Scripts\python.exe"
)

if not defined PYTHON_BIN (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_BIN=py -3"
    ) else (
        set "PYTHON_BIN=python"
    )
)

call %PYTHON_BIN% "%SCRIPT_DIR%scripts\start_system.py" --all --web %*
exit /b %errorlevel%
