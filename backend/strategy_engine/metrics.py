"""Exact expiration metrics: max profit/loss, breakevens, capital required, risk/reward.

Uses piecewise-linear expiration payoff for exact (not grid-search) breakevens.
"""

from __future__ import annotations

import math
from typing import Optional

from strategy_engine.models import StrategyLeg
from strategy_engine.payoff import strategy_payoff_at_expiration, signed_qty


def compute_breakevens(legs: list[StrategyLeg], underlying_price: float) -> list[float]:
    """Exact breakevens via piecewise-linear interpolation on expiration payoff."""
    # Collect breakpoints: 0 + all strikes
    points = {0.0}
    for leg in legs:
        if leg.instrument == "option" and leg.strike is not None:
            points.add(leg.strike)

    # Add a high point
    max_strike = max((leg.strike for leg in legs if leg.instrument == "option" and leg.strike), default=underlying_price)
    hi = max(max_strike * 3, underlying_price * 3, 1.0)
    points.add(hi)

    sorted_points = sorted(points)

    # Evaluate payoff at each point
    vals = [(p, strategy_payoff_at_expiration(legs, p)) for p in sorted_points]

    breakevens = []
    for i in range(len(vals) - 1):
        x0, y0 = vals[i]
        x1, y1 = vals[i + 1]

        if y0 == 0.0 and x0 > 0:
            breakevens.append(x0)
        elif y0 * y1 < 0:
            # Linear interpolation to find root
            x = x0 + (0 - y0) * (x1 - x0) / (y1 - y0)
            breakevens.append(x)

    if vals[-1][1] == 0.0 and vals[-1][0] > 0:
        breakevens.append(vals[-1][0])

    # Deduplicate within 1e-6
    deduped = []
    for be in sorted(breakevens):
        if not deduped or abs(be - deduped[-1]) > 1e-6:
            deduped.append(be)
    return deduped


def compute_max_profit_loss(
    legs: list[StrategyLeg], underlying_price: float
) -> tuple[Optional[float], Optional[float]]:
    """Compute max profit and max loss at expiration.

    Returns (max_profit, max_loss) where None means infinite/unlimited.
    max_profit is positive or None (unlimited upside).
    max_loss is negative or None (unlimited downside).
    """
    # Compute slope as S -> infinity
    net_shares = sum(signed_qty(leg) for leg in legs if leg.instrument == "stock")
    net_call_contracts = sum(
        signed_qty(leg) * leg.multiplier
        for leg in legs
        if leg.instrument == "option" and leg.option_type == "call"
    )
    slope_inf = net_shares + net_call_contracts

    # Compute slope as S -> 0 (put behavior)
    net_put_contracts = sum(
        signed_qty(leg) * leg.multiplier
        for leg in legs
        if leg.instrument == "option" and leg.option_type == "put"
    )
    # As S -> 0, put intrinsic = K, call intrinsic = 0, stock value = 0
    # slope at 0 is from stock legs and put legs
    slope_zero = net_shares - net_put_contracts  # negative slope means profit as S decreases

    # Evaluate payoff at all critical points
    eval_points = {0.0, 0.01}
    for leg in legs:
        if leg.instrument == "option" and leg.strike is not None:
            eval_points.add(leg.strike)
    max_strike = max((leg.strike for leg in legs if leg.instrument == "option" and leg.strike), default=underlying_price)
    hi = max(max_strike * 3, underlying_price * 3, 1.0)
    eval_points.add(hi)

    payoffs = [strategy_payoff_at_expiration(legs, p) for p in eval_points]
    finite_max = max(payoffs)
    finite_min = min(payoffs)

    # Determine unbounded directions
    if slope_inf > 0:
        max_profit = None  # unlimited upside
    else:
        max_profit = finite_max

    if slope_inf < 0:
        max_loss = None  # unlimited downside loss
    else:
        max_loss = finite_min

    # Also check if slope at zero causes unbounded loss
    # (For practical purposes, stock can go to 0 but not negative, so loss is finite)

    return max_profit, max_loss


def compute_capital_required(
    max_loss: Optional[float],
    total_entry_cashflow: float,
) -> tuple[float, bool, str]:
    """Compute capital required.

    Returns (capital_required, requires_margin, capital_method).
    """
    if max_loss is not None and math.isfinite(max_loss):
        capital = abs(max_loss)
        return capital, False, "max_loss"
    else:
        # Unlimited risk — use cash outlay as proxy
        capital = max(0.0, -total_entry_cashflow)
        return capital, True, "cash_outlay_margin"


def compute_risk_reward(
    max_profit: Optional[float],
    capital_required: float,
) -> tuple[Optional[float], Optional[str]]:
    """Compute risk/reward ratio.

    Returns (ratio, note).
    """
    if max_profit is None:
        return None, "Unlimited max profit"
    if capital_required <= 0:
        return None, "No capital required"
    return max_profit / capital_required, None
