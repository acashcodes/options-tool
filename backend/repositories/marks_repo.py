"""Marks repository — stores daily mark prices for day P&L computation.

Each position's mark is recorded once per trading day. Day P&L is computed
as the difference between today's mark and the prior trading day's mark.
"""

from __future__ import annotations

from typing import Optional
from datetime import date, timedelta

from db import get_db
import time_utils


def _trading_date_today() -> str:
    """Current ET trading date as YYYY-MM-DD."""
    return time_utils.now_et().strftime("%Y-%m-%d")


def _prior_trading_date(ref_date: str) -> str:
    """Find the most recent prior trading date (skips weekends).

    Does not account for market holidays — a future improvement.
    """
    from datetime import datetime
    d = datetime.strptime(ref_date, "%Y-%m-%d").date()
    d -= timedelta(days=1)
    while d.weekday() >= 5:  # Saturday=5, Sunday=6
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def upsert_mark(
    as_of_date: str,
    ticker: str,
    asset_type: str,
    mark_price_val: float,
    mark_source: str = "mid",
    strike: float = None,
    expiration: str = None,
) -> None:
    """Insert or update a mark for a position on a given date."""
    ts = time_utils.now_et().isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO marks (as_of_date, as_of_ts, ticker, asset_type, strike, expiration, mark_price, mark_source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(as_of_date, ticker, asset_type, strike, expiration)
               DO UPDATE SET mark_price=excluded.mark_price, mark_source=excluded.mark_source, as_of_ts=excluded.as_of_ts""",
            (as_of_date, ts, ticker.upper(), asset_type, strike, expiration, mark_price_val, mark_source),
        )


def get_mark(
    as_of_date: str,
    ticker: str,
    asset_type: str,
    strike: float = None,
    expiration: str = None,
) -> Optional[float]:
    """Get the mark price for a position on a specific date."""
    with get_db() as conn:
        if strike is not None:
            row = conn.execute(
                """SELECT mark_price FROM marks
                   WHERE as_of_date=? AND ticker=? AND asset_type=? AND strike=? AND expiration=?""",
                (as_of_date, ticker.upper(), asset_type, strike, expiration),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT mark_price FROM marks
                   WHERE as_of_date=? AND ticker=? AND asset_type=? AND strike IS NULL""",
                (as_of_date, ticker.upper(), asset_type),
            ).fetchone()
    return row["mark_price"] if row else None


def get_prior_mark(
    ticker: str,
    asset_type: str,
    strike: float = None,
    expiration: str = None,
) -> Optional[float]:
    """Get the prior trading day's mark price for day P&L computation."""
    today = _trading_date_today()
    prior_date = _prior_trading_date(today)
    return get_mark(prior_date, ticker, asset_type, strike, expiration)


def record_today_mark(
    ticker: str,
    asset_type: str,
    mark_price_val: float,
    mark_source: str = "mid",
    strike: float = None,
    expiration: str = None,
) -> None:
    """Record today's mark for a position."""
    today = _trading_date_today()
    upsert_mark(today, ticker, asset_type, mark_price_val, mark_source, strike, expiration)


def cleanup_old_marks(days_to_keep: int = 90) -> int:
    """Remove marks older than N days."""
    cutoff = (date.today() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM marks WHERE as_of_date < ?", (cutoff,))
    return cursor.rowcount
