"""Strategy analysis endpoint: /api/strategy/analyze

The canonical backend endpoint for computing payoff curves, metrics,
breakevens, max profit/loss, capital required, and probability of profit.
Frontend should use this exclusively instead of client-side math.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from data_provider import DataProvider
from strategy_engine.models import AnalyzeRequest, PricingAssumptions
from strategy_engine.payoff import strategy_payoff_at_expiration
from strategy_engine.pricing import leg_entry_cashflow
from strategy_engine.metrics import (
    compute_breakevens,
    compute_max_profit_loss,
    compute_capital_required,
    compute_risk_reward,
)
from strategy_engine.curve import expiration_curve, mtm_curve
from strategy_engine.probability import compute_pop
from formatting import money


def create_strategy_routes(provider: DataProvider) -> APIRouter:
    router = APIRouter(prefix="/api/strategy", tags=["strategy"])

    @router.post("/analyze")
    def analyze(req: AnalyzeRequest):
        """Analyze a multi-leg options/stock strategy.

        Returns metrics, curves, breakevens, PoP — all from canonical math.
        """
        try:
            legs = req.legs
            S0 = req.underlying.price

            # Fill default assumptions
            assumptions = req.assumptions or PricingAssumptions()
            r = assumptions.risk_free_rate
            q = req.underlying.dividend_yield or assumptions.dividend_yield

            # Entry cashflows
            entry_cashflows = [leg_entry_cashflow(leg) for leg in legs]
            total_entry_cashflow = sum(entry_cashflows)

            # Split by instrument type
            options_cf = sum(
                cf for leg, cf in zip(legs, entry_cashflows)
                if leg.instrument == "option"
            )
            stock_cf = sum(
                cf for leg, cf in zip(legs, entry_cashflows)
                if leg.instrument == "stock"
            )

            # Net premium (for options-only: same as entry_cashflow of options)
            net_premium = options_cf

            # Max profit / loss
            max_profit, max_loss = compute_max_profit_loss(legs, S0)

            # Breakevens
            breakevens = compute_breakevens(legs, S0)

            # Capital required
            capital, requires_margin, capital_method = compute_capital_required(
                max_loss, total_entry_cashflow
            )

            # Risk/reward
            rr, rr_note = compute_risk_reward(max_profit, capital)

            # Curves
            exp_curve = expiration_curve(legs, S0, req.curve_points)
            mtm = mtm_curve(legs, S0, req.days_forward, r=r, q=q, points=req.curve_points)

            # Probability of profit
            pop = compute_pop(legs, S0, r=r, q=q)

            # Count IV quality
            missing_iv = sum(
                1 for leg in legs
                if leg.instrument == "option" and (leg.iv is None or leg.iv <= 0)
            )

            return {
                "underlying_price": S0,
                "assumptions_used": {
                    "risk_free_rate": r,
                    "dividend_yield": q,
                    "model": assumptions.model,
                    "day_count": assumptions.day_count,
                },
                "entry_cashflow_total": money(total_entry_cashflow),
                "entry_cashflow_options": money(options_cf),
                "entry_cashflow_stock": money(stock_cf),
                "net_premium": money(net_premium),
                "capital_required": money(capital),
                "requires_margin": requires_margin,
                "capital_method": capital_method,
                "max_profit": money(max_profit) if max_profit is not None else None,
                "max_loss": money(max_loss) if max_loss is not None else None,
                "breakevens": [money(be) for be in breakevens],
                "risk_reward": money(rr, 2) if rr is not None else None,
                "risk_reward_note": rr_note,
                "curves": {
                    "expiration": [
                        {"price": money(p["price"]), "pl": money(p["pl"])}
                        for p in exp_curve
                    ],
                    "mtm": [
                        {"price": money(p["price"]), "pl": money(p["pl"])}
                        for p in mtm
                    ],
                },
                "pop": pop,
                "data_quality": {
                    "missing_iv_legs": missing_iv,
                },
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=400, detail=str(e))

    return router
