#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
fi

exec "${PYTHON_BIN}" "${PROJECT_DIR}/scripts/start_system.py" --all --web "$@"
