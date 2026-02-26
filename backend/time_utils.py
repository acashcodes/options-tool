"""Timezone-aware time-to-expiry utilities.

Uses ET (America/New_York) and ACT/365 day count convention.
Fixes 0DTE bugs by computing seconds-level precision instead of date-only diffs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")
EXPIRY_HOUR = 16  # 4:00 PM ET
SECONDS_IN_YEAR = 365.0 * 24 * 60 * 60  # ACT/365


def now_et() -> datetime:
    """Current datetime in Eastern Time."""
    return datetime.now(NY_TZ)


def expiry_dt_et(expiration_date: str) -> datetime:
    """Convert expiration date string (YYYY-MM-DD) to 4:00 PM ET datetime."""
    d = datetime.strptime(expiration_date, "%Y-%m-%d")
    return d.replace(hour=EXPIRY_HOUR, minute=0, second=0, microsecond=0, tzinfo=NY_TZ)


def year_frac_to(expiration_date: str, as_of: datetime | None = None) -> float:
    """Time to expiration in years (ACT/365, seconds precision).

    Returns 0.0 if already past expiry.
    """
    if as_of is None:
        as_of = now_et()
    elif as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=NY_TZ)
    exp = expiry_dt_et(expiration_date)
    secs = (exp - as_of).total_seconds()
    return max(secs, 0.0) / SECONDS_IN_YEAR


def days_to(expiration_date: str, as_of: datetime | None = None) -> float:
    """Time to expiration in days (seconds / 86400)."""
    if as_of is None:
        as_of = now_et()
    elif as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=NY_TZ)
    exp = expiry_dt_et(expiration_date)
    secs = (exp - as_of).total_seconds()
    return max(secs, 0.0) / 86400.0
