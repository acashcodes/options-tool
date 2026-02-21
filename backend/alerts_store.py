"""JSON-file persistence for dismissed alerts and custom alert thresholds."""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
ALERTS_FILE = DATA_DIR / "alerts_config.json"

_DEFAULT = {
    "dismissed": [],       # list of alert ID strings
    "thresholds": {
        "earnings_days": 7,
        "iv_high": 80,
        "iv_low": 20,
        "large_move_pct": 3,
        "expiration_days": 7,
    },
}


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if not ALERTS_FILE.exists():
        return {**_DEFAULT, "dismissed": list(_DEFAULT["dismissed"]),
                "thresholds": dict(_DEFAULT["thresholds"])}
    try:
        raw = json.loads(ALERTS_FILE.read_text())
        # Merge defaults for missing keys
        thresholds = {**_DEFAULT["thresholds"], **raw.get("thresholds", {})}
        return {
            "dismissed": raw.get("dismissed", []),
            "thresholds": thresholds,
        }
    except (json.JSONDecodeError, Exception):
        return {**_DEFAULT, "dismissed": list(_DEFAULT["dismissed"]),
                "thresholds": dict(_DEFAULT["thresholds"])}


def _save(data: dict) -> None:
    _ensure_dir()
    ALERTS_FILE.write_text(json.dumps(data, indent=2))


def get_thresholds() -> dict:
    return _load()["thresholds"]


def set_thresholds(thresholds: dict) -> dict:
    data = _load()
    data["thresholds"] = {**data["thresholds"], **thresholds}
    _save(data)
    return data["thresholds"]


def get_dismissed() -> list[str]:
    return _load()["dismissed"]


def dismiss_alert(alert_id: str) -> list[str]:
    data = _load()
    if alert_id not in data["dismissed"]:
        data["dismissed"].append(alert_id)
    _save(data)
    return data["dismissed"]


def restore_alert(alert_id: str) -> list[str]:
    data = _load()
    data["dismissed"] = [d for d in data["dismissed"] if d != alert_id]
    _save(data)
    return data["dismissed"]


def clear_dismissed() -> list[str]:
    data = _load()
    data["dismissed"] = []
    _save(data)
    return []
