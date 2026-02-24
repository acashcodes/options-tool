"""Output formatting helpers. Rounding belongs here, NOT in core math."""

from __future__ import annotations

from typing import Optional


def money(x: float | None, decimals: int = 2) -> float | None:
    """Round to cents for display only."""
    if x is None:
        return None
    return round(x, decimals)


def pct(x: float | None, decimals: int = 2) -> float | None:
    """Round percentage for display only."""
    if x is None:
        return None
    return round(x, decimals)


def greek(x: float | None, decimals: int = 4) -> float | None:
    """Round a Greek value for display only."""
    if x is None:
        return None
    return round(x, decimals)
