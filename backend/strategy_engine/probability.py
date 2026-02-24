"""Probability of profit using log-normal risk-neutral model."""

from __future__ import annotations

from strategy_engine.models import StrategyLeg
from strategy_engine.payoff import strategy_payoff_at_expiration
from strategy_engine.metrics import compute_breakevens
from greeks import prob_above
import time_utils


def compute_pop(
    legs: list[StrategyLeg],
    underlying_price: float,
    r: float = 0.045,
    q: float = 0.0,
) -> dict | None:
    """Compute probability of profit using breakevens and log-normal model.

    Returns dict with value (0-100%), model name, horizon.
    """
    if not legs:
        return None

    breakevens = compute_breakevens(legs, underlying_price)

    # Get average IV and earliest expiration
    total_iv = 0.0
    iv_count = 0
    earliest_exp = None
    for leg in legs:
        if leg.instrument == "option":
            if leg.iv is not None and leg.iv > 0:
                total_iv += leg.iv
                iv_count += 1
            if leg.expiration:
                if earliest_exp is None or leg.expiration < earliest_exp:
                    earliest_exp = leg.expiration

    if iv_count == 0 or earliest_exp is None:
        return None

    sigma = total_iv / iv_count
    t_years = time_utils.year_frac_to(earliest_exp)
    if t_years <= 0:
        return None

    # Find profit regions by testing between breakevens and extremes
    max_strike = max(
        (leg.strike for leg in legs if leg.instrument == "option" and leg.strike),
        default=underlying_price
    )
    hi = max(max_strike * 3, underlying_price * 3)

    sorted_be = sorted(breakevens)
    test_points = [0.01] + sorted_be + [hi]

    profit_prob = 0.0
    for i in range(len(test_points) - 1):
        lo = test_points[i]
        hi_pt = test_points[i + 1]
        mid = (lo + hi_pt) / 2
        pl = strategy_payoff_at_expiration(legs, mid)

        if pl > 0:
            p_above_lo = prob_above(underlying_price, lo, t_years, r, sigma, q)
            if i + 1 < len(test_points) - 1:
                p_above_hi = prob_above(underlying_price, hi_pt, t_years, r, sigma, q)
                region_prob = p_above_lo - p_above_hi
            else:
                region_prob = p_above_lo
            profit_prob += max(0, region_prob)

    pop_pct = max(0, min(100, profit_prob * 100))

    return {
        "value": pop_pct,
        "model": "lognormal_risk_neutral",
        "as_of": time_utils.now_et().isoformat(),
        "horizon": "earliest_expiration",
    }
