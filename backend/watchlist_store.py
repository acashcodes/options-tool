"""JSON-file persistence layer for the watchlist."""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_watchlist() -> list[str]:
    """Return list of ticker strings."""
    _ensure_dir()
    if not WATCHLIST_FILE.exists():
        return []
    try:
        raw = json.loads(WATCHLIST_FILE.read_text())
        return [str(t).upper() for t in raw if isinstance(t, str)]
    except (json.JSONDecodeError, Exception):
        return []


def save_watchlist(tickers: list[str]) -> None:
    _ensure_dir()
    WATCHLIST_FILE.write_text(json.dumps(tickers, indent=2))


def add_ticker(ticker: str) -> list[str]:
    """Add ticker if not already present. Returns updated list."""
    tickers = load_watchlist()
    t = ticker.upper().strip()
    if t and t not in tickers:
        tickers.append(t)
        save_watchlist(tickers)
    return tickers


def remove_ticker(ticker: str) -> list[str]:
    """Remove ticker. Returns updated list."""
    tickers = load_watchlist()
    t = ticker.upper().strip()
    new_tickers = [x for x in tickers if x != t]
    save_watchlist(new_tickers)
    return new_tickers
