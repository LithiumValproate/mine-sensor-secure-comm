"""Configuration loading helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_json(path: str | Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    with Path(path).open('r', encoding='utf-8') as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML object from disk."""
    with Path(path).open('r', encoding='utf-8') as config_file:
        data = yaml.safe_load(config_file)
    if not isinstance(data, dict):
        raise ValueError(f"expected YAML object in {path}")
    return data


def load_psk_map(path: str | Path) -> dict[str, str]:
    """Load sensor_id to PSK hex mapping."""
    raw = load_json(path)
    psk_map: dict[str, str] = {}
    for sensor_id, entry in raw.items():
        if not isinstance(entry, dict):
            raise ValueError(f"PSK entry for {sensor_id} must be an object")
        psk_id = entry.get('psk_id')
        psk_hex = entry.get('psk_hex')
        if psk_id != sensor_id:
            raise ValueError(f"PSK id mismatch for {sensor_id}")
        if not isinstance(psk_hex, str):
            raise ValueError(f"PSK hex missing for {sensor_id}")
        psk_map[sensor_id] = psk_hex
    return psk_map
