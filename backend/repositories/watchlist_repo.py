"""Watchlist repository — SQLite backed."""

from __future__ import annotations

from db import get_db


def load_watchlist() -> list[str]:
    with get_db() as conn:
        rows = conn.execute("SELECT ticker FROM watchlist ORDER BY ticker").fetchall()
    return [r["ticker"] for r in rows]


def add_ticker(ticker: str) -> list[str]:
    t = ticker.upper().strip()
    if not t:
        return load_watchlist()
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO watchlist (ticker) VALUES (?)", (t,))
    return load_watchlist()


def remove_ticker(ticker: str) -> list[str]:
    t = ticker.upper().strip()
    with get_db() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker=?", (t,))
    return load_watchlist()
