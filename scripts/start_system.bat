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

call %PYTHON_BIN% "%SCRIPT_DIR%start_system.py" --all --web %*
exit /b %errorlevel%
