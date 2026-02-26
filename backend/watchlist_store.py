"""Watchlist store — delegates to SQLite repository.

Maintains the same public interface so routes don't need changes.
"""

from __future__ import annotations

from repositories.watchlist_repo import (
    load_watchlist,
    add_ticker,
    remove_ticker,
)

__all__ = [
    "load_watchlist",
    "add_ticker",
    "remove_ticker",
]
