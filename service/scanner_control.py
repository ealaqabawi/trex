"""Persistent alert-only control flag shared by the local dashboard and n8n."""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "logs" / "scanner_control.json"
_LOCK = threading.Lock()


def read_state(path: Path = STATE_PATH) -> dict:
    with _LOCK:
        return _read_state(path)


def _read_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}

    return {
        "enabled": state.get("enabled") is True,
        "updated_at": state.get("updated_at"),
        "last_gate_check": state.get("last_gate_check"),
    }


def _write_state(state: dict, path: Path) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path.write_text(json.dumps(state) + "\n")
    os.replace(temporary_path, path)


def set_enabled(enabled: bool, path: Path = STATE_PATH) -> dict:
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")

    state = {
        "enabled": enabled,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _LOCK:
        previous = _read_state(path)
        state["last_gate_check"] = previous["last_gate_check"]
        _write_state(state, path)

    return state


def mark_gate_check(path: Path = STATE_PATH) -> dict:
    with _LOCK:
        state = _read_state(path)
        state["last_gate_check"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_state(state, path)
    return state
