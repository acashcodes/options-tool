"""Expiration payoff functions — exact, deterministic.

These functions define the canonical payoff at expiration for any leg or strategy.
"""

from __future__ import annotations

from strategy_engine.models import StrategyLeg


def signed_qty(leg: StrategyLeg) -> float:
    """Convert action to signed quantity: +qty for BUY, -qty for SELL."""
    return leg.quantity if leg.action == "buy" else -leg.quantity


def payoff_at_expiration(leg: StrategyLeg, S: float) -> float:
    """P&L for a single leg at expiration (in dollars).

    For options: includes the entry cost (premium paid/received).
    For stock: P&L from entry price.
    """
    q = signed_qty(leg)
    if leg.instrument == "stock":
        return q * (S - leg.entry_price)

    # Option leg
    assert leg.option_type is not None and leg.strike is not None
    intrinsic = (
        max(0.0, S - leg.strike) if leg.option_type == "call"
        else max(0.0, leg.strike - S)
    )
    return q * leg.multiplier * (intrinsic - leg.entry_price)


def strategy_payoff_at_expiration(legs: list[StrategyLeg], S: float) -> float:
    """Total strategy P&L at expiration."""
    return sum(payoff_at_expiration(leg, S) for leg in legs)
