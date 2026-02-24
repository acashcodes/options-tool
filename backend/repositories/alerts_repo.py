"""Alerts repository — SQLite backed."""

from __future__ import annotations

import json
from db import get_db

_DEFAULT_THRESHOLDS = {
    "earnings_days": 7,
    "iv_high": 80,
    "iv_low": 20,
    "large_move_pct": 3,
    "expiration_days": 7,
}


def get_thresholds() -> dict:
    result = dict(_DEFAULT_THRESHOLDS)
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM alert_config").fetchall()
    for r in rows:
        try:
            result[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            result[r["key"]] = r["value"]
    return result


def set_thresholds(thresholds: dict) -> dict:
    with get_db() as conn:
        for k, v in thresholds.items():
            conn.execute(
                "INSERT OR REPLACE INTO alert_config (key, value) VALUES (?, ?)",
                (k, json.dumps(v)),
            )
    return get_thresholds()


def get_dismissed() -> list[str]:
    with get_db() as conn:
        rows = conn.execute("SELECT alert_id FROM dismissed_alerts").fetchall()
    return [r["alert_id"] for r in rows]


def dismiss_alert(alert_id: str) -> list[str]:
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO dismissed_alerts (alert_id) VALUES (?)",
            (alert_id,),
        )
    return get_dismissed()


def restore_alert(alert_id: str) -> list[str]:
    with get_db() as conn:
        conn.execute("DELETE FROM dismissed_alerts WHERE alert_id=?", (alert_id,))
    return get_dismissed()


def clear_dismissed() -> list[str]:
    with get_db() as conn:
        conn.execute("DELETE FROM dismissed_alerts")
    return []
