"""Payoff curve generation: expiration + mark-to-market.

Uses numpy.linspace for deterministic grid to avoid float accumulation errors.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from strategy_engine.models import StrategyLeg
from strategy_engine.payoff import strategy_payoff_at_expiration
from strategy_engine.pricing import leg_current_value, leg_entry_cashflow
import time_utils


def default_price_grid(
    S0: float, strikes: list[float], points: int = 200
) -> tuple[float, float, list[float]]:
    """Generate a deterministic price grid for curve evaluation."""
    min_strike = min(strikes) if strikes else S0
    max_strike = max(strikes) if strikes else S0
    padding = max(0.15 * S0, 1.5 * (max_strike - min_strike or 0.2 * S0))
    price_min = max(0.01, min_strike - padding)
    price_max = max_strike + padding
    grid = np.linspace(price_min, price_max, points).tolist()
    return price_min, price_max, grid


def expiration_curve(
    legs: list[StrategyLeg], S0: float, points: int = 200
) -> list[dict]:
    """Generate expiration P&L curve."""
    strikes = [leg.strike for leg in legs if leg.instrument == "option" and leg.strike is not None]
    _, _, grid = default_price_grid(S0, strikes, points)

    curve = []
    for p in grid:
        pl = strategy_payoff_at_expiration(legs, p)
        curve.append({"price": p, "pl": pl})
    return curve


def mtm_curve(
    legs: list[StrategyLeg],
    S0: float,
    days_forward: int,
    r: float = 0.045,
    q: float = 0.0,
    points: int = 200,
) -> list[dict]:
    """Generate mark-to-market P&L curve at eval_date = now + days_forward."""
    strikes = [leg.strike for leg in legs if leg.instrument == "option" and leg.strike is not None]
    _, _, grid = default_price_grid(S0, strikes, points)

    eval_dt = time_utils.now_et() + timedelta(days=days_forward)

    # Total entry cashflow
    total_entry_cf = sum(leg_entry_cashflow(leg) for leg in legs)

    curve = []
    for p in grid:
        total_value = sum(leg_current_value(leg, p, eval_dt=eval_dt, r=r, q=q) for leg in legs)
        pl = total_value + total_entry_cf
        curve.append({"price": p, "pl": pl})
    return curve
