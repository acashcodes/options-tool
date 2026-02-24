"""Mark-to-market valuation and entry/fill pricing.

Defines the canonical pricing conventions:
- entry_cashflow: BUY = negative (cash out), SELL = positive (cash in)
- current_value: long = positive, short = negative
- pnl = current_value + entry_cashflow
"""

from __future__ import annotations

from typing import Optional

from strategy_engine.models import StrategyLeg, Action
from greeks import bs_price
import time_utils


# ---------------------------------------------------------------------------
# Model pricing
# ---------------------------------------------------------------------------

def option_model_price(
    S: float, K: float, t: float, r: float, q: float, sigma: float,
    option_type: str,
) -> float:
    """BSM theoretical price for an option."""
    return bs_price(S, K, t, r, sigma, option_type, q=q)


# ---------------------------------------------------------------------------
# Entry cost conventions
# ---------------------------------------------------------------------------

def leg_entry_cashflow(leg: StrategyLeg) -> float:
    """Cash flow at entry. BUY = negative (paid), SELL = positive (received).

    entry_cashflow = -signed_qty * units * entry_price
    """
    sq = leg.quantity if leg.action == "buy" else -leg.quantity
    if leg.instrument == "stock":
        return -sq * leg.entry_price
    return -sq * leg.multiplier * leg.entry_price


def leg_current_value(
    leg: StrategyLeg, S: float, eval_dt=None,
    r: float = 0.045, q: float = 0.0,
) -> float:
    """Current position value at evaluation time.

    current_value = signed_qty * units * current_price
    """
    sq = leg.quantity if leg.action == "buy" else -leg.quantity
    if leg.instrument == "stock":
        return sq * S

    # Option
    assert leg.expiration is not None and leg.strike is not None
    t = time_utils.year_frac_to(leg.expiration, as_of=eval_dt)
    if t <= 0:
        # At/past expiration: intrinsic value
        intrinsic = (
            max(0.0, S - leg.strike) if leg.option_type == "call"
            else max(0.0, leg.strike - S)
        )
        current_price = intrinsic
    else:
        sigma = leg.iv if leg.iv is not None else 0.30
        current_price = option_model_price(S, leg.strike, t, r, q, sigma, leg.option_type)

    return sq * leg.multiplier * current_price


# ---------------------------------------------------------------------------
# Execution-realistic pricing (WP5)
# ---------------------------------------------------------------------------

def mark_price(bid: float | None, ask: float | None, last: float | None) -> float | None:
    """Mid price if bid/ask valid, else last."""
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2
    if last is not None and last > 0:
        return last
    return None


def entry_fill_price(
    action: str,
    bid: float | None,
    ask: float | None,
    last: float | None,
    mode: str = "mid",
    slippage_pct: float = 0.0,
) -> float | None:
    """Compute fill price based on pricing mode.

    Modes:
    - "mid": (bid+ask)/2
    - "conservative": buys use ask, sells use bid
    - "mid_slippage": mid +/- slippage_pct * spread
    """
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread = ask - bid

        if mode == "conservative":
            return ask if action == "buy" else bid
        elif mode == "mid_slippage":
            if action == "buy":
                price = mid + slippage_pct * spread
                return min(price, ask)  # clamp
            else:
                price = mid - slippage_pct * spread
                return max(price, bid)  # clamp
        else:  # "mid"
            return mid

    # Fallback
    if last is not None and last > 0:
        return last
    return None
