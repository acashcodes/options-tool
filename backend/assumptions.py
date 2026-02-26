"""Central assumptions: risk-free rate from ^TNX, default dividend yield, day count.

Single source of truth so frontend/backend never drift.
"""

from __future__ import annotations

from typing import Any, Optional


# --- ^TNX scaling ---

def tnx_to_yield_decimal(tnx_index_price: float | None) -> float | None:
    """Convert ^TNX index price to yield as a decimal.

    ^TNX is typically 10x the yield percentage.
    E.g., 44.50 -> 4.45% -> 0.0445
    """
    if tnx_index_price is None:
        return None
    return tnx_index_price / 1000.0


def tnx_to_yield_percent(tnx_index_price: float | None) -> float | None:
    """Convert ^TNX index price to yield percentage.

    E.g., 44.50 -> 4.45
    """
    if tnx_index_price is None:
        return None
    return tnx_index_price / 10.0


_FALLBACK_RISK_FREE_RATE = 0.045


def default_risk_free_rate(provider: Any) -> float:
    """Fetch risk-free rate from ^TNX, with fallback.

    Returns decimal (e.g. 0.0445 for 4.45%).
    """
    try:
        q = provider.get_quote_light("^TNX")
        price = q.get("price")
        rate = tnx_to_yield_decimal(price)
        if rate is not None and rate > 0:
            return rate
    except Exception:
        pass
    return _FALLBACK_RISK_FREE_RATE


def get_assumptions_dict(provider: Any) -> dict:
    """Build the full assumptions response dict."""
    import time_utils

    r = default_risk_free_rate(provider)

    # Get TNX raw price for display
    tnx_yield_pct = None
    try:
        q = provider.get_quote_light("^TNX")
        tnx_yield_pct = tnx_to_yield_percent(q.get("price"))
    except Exception:
        pass

    return {
        "as_of": time_utils.now_et().isoformat(),
        "risk_free_rate": r,
        "risk_free_source": "^TNX",
        "tnx_yield_percent": tnx_yield_pct,
        "dividend_yield_default": 0.0,
        "day_count": "ACT/365",
        "default_pricing_mode": "mid",
        "default_slippage_pct_of_spread": 0.0,
    }
