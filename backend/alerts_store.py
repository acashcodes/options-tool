"""Alerts store — delegates to SQLite repository.

Maintains the same public interface so routes don't need changes.
"""

from __future__ import annotations

from repositories.alerts_repo import (
    get_thresholds,
    set_thresholds,
    get_dismissed,
    dismiss_alert,
    restore_alert,
    clear_dismissed,
)

__all__ = [
    "get_thresholds",
    "set_thresholds",
    "get_dismissed",
    "dismiss_alert",
    "restore_alert",
    "clear_dismissed",
]
