"""Strategy Recommender – aligned with canonical strategy_engine.

Deterministic engine that evaluates option strategies based on user-defined
target price and date, computes payoff at target at expiration, and ranks
by capital efficiency (risk-reward = payoff_at_target / capital_required).

All payoff/metrics math defers to strategy_engine for consistency.
"""

from __future__ import annotations

import math
from datetime import datetime, date
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from data_provider.base import DataProvider
from strategy_engine.models import StrategyLeg
from strategy_engine.payoff import strategy_payoff_at_expiration
from strategy_engine.metrics import (
    compute_breakevens,
    compute_max_profit_loss,
    compute_capital_required,
    compute_risk_reward,
)
from strategy_engine.pricing import mark_price, entry_fill_price, leg_entry_cashflow
from strategy_engine.curve import expiration_curve
from formatting import money


# ── API ─────────────────────────────────────────────────────


class RecommendRequest(BaseModel):
    ticker: str
    target_price: float
    target_date: str  # YYYY-MM-DD
    pricing_mode: str = "mid"
    slippage_pct: float = 0.0


def create_recommender_routes(provider: DataProvider) -> APIRouter:
    router = APIRouter(prefix="/api/recommend", tags=["recommender"])

    @router.post("")
    def recommend(req: RecommendRequest):
        try:
            results, direction, expiration_used = _recommend(
                provider, req.ticker, req.target_price, req.target_date,
                pricing_mode=req.pricing_mode,
                slippage_pct=req.slippage_pct,
            )
            return {
                "recommendations": results,
                "direction": direction,
                "expiration_used": expiration_used,
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(e))

    return router


# ── Core Engine ──────────────────────────────────────────────


def _recommend(provider, ticker, target_price, target_date,
               pricing_mode="mid", slippage_pct=0.0):
    ticker = ticker.upper()
    quote = provider.get_quote(ticker)
    current_price = quote.get("price")
    if not current_price or current_price <= 0:
        return [], None, None

    # ── 1. Select expiration: on or just after target date ──
    expirations = provider.get_options_expirations(ticker)
    if not expirations:
        return [], None, None

    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    on_or_after = [e for e in expirations if _parse_date(e) >= target_dt]
    if on_or_after:
        best_exp = min(on_or_after, key=lambda e: (_parse_date(e) - target_dt).days)
    else:
        best_exp = min(expirations, key=lambda e: abs((_parse_date(e) - target_dt).days))

    # ── 2. Load chain, filter for liquidity ──
    chain = provider.get_options_chain(ticker, best_exp)
    calls = sorted(
        [c for c in chain.get("calls", []) if _liquid(c) and _get_mid(c) > 0],
        key=lambda c: c["strike"],
    )
    puts = sorted(
        [p for p in chain.get("puts", []) if _liquid(p) and _get_mid(p) > 0],
        key=lambda p: p["strike"],
    )
    if not calls and not puts:
        return [], None, best_exp

    # ── 3. Determine direction from target vs current ──
    if target_price > current_price * 1.001:
        direction = "bullish"
    elif target_price < current_price * 0.999:
        direction = "bearish"
    else:
        direction = "neutral"

    # ── 4. Generate candidates ──
    candidates = []
    if direction == "bullish":
        if calls:
            candidates += _gen_long_calls(calls, current_price, target_price, best_exp, pricing_mode, slippage_pct)
            candidates += _gen_call_debit_spreads(calls, current_price, target_price, best_exp, pricing_mode, slippage_pct)
        if puts:
            candidates += _gen_put_credit_spreads(puts, current_price, target_price, best_exp, pricing_mode, slippage_pct)
    elif direction == "bearish":
        if puts:
            candidates += _gen_long_puts(puts, current_price, target_price, best_exp, pricing_mode, slippage_pct)
            candidates += _gen_put_debit_spreads(puts, current_price, target_price, best_exp, pricing_mode, slippage_pct)
        if calls:
            candidates += _gen_call_credit_spreads(calls, current_price, target_price, best_exp, pricing_mode, slippage_pct)
    else:  # neutral
        if calls and puts:
            candidates += _gen_iron_condors(calls, puts, current_price, target_price, best_exp, pricing_mode, slippage_pct)

    # ── 5. Filter: payoff must be > 0 and capital must be > 0 ──
    valid = [c for c in candidates if c["payoff_at_target"] > 0 and c["capital_required"] > 0]

    # ── 6. Sort by risk-reward descending ──
    valid.sort(key=lambda x: x["risk_reward"], reverse=True)

    # ── 7. Return top 5 with payoff curves ──
    top = valid[:5]
    for item in top:
        # Use canonical curve generation
        strategy_legs = _to_strategy_legs(item["legs"], best_exp)
        curve_data = expiration_curve(strategy_legs, current_price, points=50)
        item["curve"] = [{"price": money(p["price"]), "pl": money(p["pl"])} for p in curve_data]
        item["current_price"] = current_price
        item["ticker"] = ticker

    return top, direction, best_exp


# ── Canonical engine integration ─────────────────────────────


def _to_strategy_legs(ui_legs: list[dict], expiration: str) -> list[StrategyLeg]:
    """Convert recommender UI leg dicts to canonical StrategyLeg models."""
    result = []
    for leg in ui_legs:
        result.append(StrategyLeg(
            instrument="option",
            option_type="call" if leg["type"] == "Call" else "put",
            action=leg["action"],
            quantity=leg["quantity"],
            strike=leg["strike"],
            expiration=leg.get("expiration", expiration),
            iv=leg.get("iv"),
            multiplier=100,
            entry_price=leg["premium"],
            bid=leg.get("bid"),
            ask=leg.get("ask"),
        ))
    return result


def _compute_canonical_metrics(ui_legs: list[dict], current_price: float, target_price: float,
                                expiration: str) -> dict:
    """Use canonical strategy_engine to compute metrics for a set of legs."""
    strategy_legs = _to_strategy_legs(ui_legs, expiration)

    # Payoff at target
    payoff_at_target = strategy_payoff_at_expiration(strategy_legs, target_price)

    # Canonical metrics
    max_profit, max_loss = compute_max_profit_loss(strategy_legs, current_price)
    breakevens = compute_breakevens(strategy_legs, current_price)
    total_entry_cf = sum(leg_entry_cashflow(leg) for leg in strategy_legs)
    capital, requires_margin, capital_method = compute_capital_required(max_loss, total_entry_cf)

    # Risk/reward based on payoff at target vs capital
    if capital > 0 and payoff_at_target > 0:
        rr = payoff_at_target / capital
    else:
        rr = 0.0

    return {
        "payoff_at_target": money(payoff_at_target),
        "max_profit": money(max_profit) if max_profit is not None else None,
        "max_loss": money(max_loss) if max_loss is not None else None,
        "breakevens": [money(be) for be in breakevens],
        "capital_required": money(capital),
        "requires_margin": requires_margin,
        "net_premium": money(total_entry_cf),
        "risk_reward": money(rr, 2) if rr else 0.0,
    }


# ── Strategy Generators ──────────────────────────────────────


def _gen_long_calls(calls, S0, St, exp, pricing_mode, slippage_pct):
    results = []
    for opt in calls:
        K = opt["strike"]
        if K < S0 * 0.85 or K > S0 * 2.0:
            continue
        prem = _fill_price(opt, "buy", pricing_mode, slippage_pct)
        if prem <= 0:
            continue

        legs = [_make_leg("Call", opt, "buy", exp, prem)]
        metrics = _compute_canonical_metrics(legs, S0, St, exp)
        if metrics["payoff_at_target"] <= 0 or metrics["capital_required"] <= 0:
            continue

        results.append({
            "name": f"Long ${K:g} Call",
            "strategy_type": "Long Call",
            "legs": legs,
            "expiration": exp,
            "strikes": [K],
            **metrics,
        })
    return results


def _gen_long_puts(puts, S0, St, exp, pricing_mode, slippage_pct):
    results = []
    for opt in puts:
        K = opt["strike"]
        if K < S0 * 0.01 or K > S0 * 1.15:
            continue
        prem = _fill_price(opt, "buy", pricing_mode, slippage_pct)
        if prem <= 0:
            continue

        legs = [_make_leg("Put", opt, "buy", exp, prem)]
        metrics = _compute_canonical_metrics(legs, S0, St, exp)
        if metrics["payoff_at_target"] <= 0 or metrics["capital_required"] <= 0:
            continue

        results.append({
            "name": f"Long ${K:g} Put",
            "strategy_type": "Long Put",
            "legs": legs,
            "expiration": exp,
            "strikes": [K],
            **metrics,
        })
    return results


def _gen_call_debit_spreads(calls, S0, St, exp, pricing_mode, slippage_pct):
    results = []
    buys = _subsample([c for c in calls if S0 * 0.85 <= c["strike"] <= S0 * 1.15], 10)
    sells = _subsample([c for c in calls if S0 * 0.85 <= c["strike"] <= S0 * 2.0], 12)

    for buy_opt in buys:
        K1 = buy_opt["strike"]
        prem1 = _fill_price(buy_opt, "buy", pricing_mode, slippage_pct)
        for sell_opt in sells:
            K2 = sell_opt["strike"]
            if K2 <= K1:
                continue
            prem2 = _fill_price(sell_opt, "sell", pricing_mode, slippage_pct)
            if prem1 - prem2 <= 0:
                continue

            legs = [
                _make_leg("Call", buy_opt, "buy", exp, prem1),
                _make_leg("Call", sell_opt, "sell", exp, prem2),
            ]
            metrics = _compute_canonical_metrics(legs, S0, St, exp)
            if metrics["payoff_at_target"] <= 0 or metrics["capital_required"] <= 0:
                continue

            results.append({
                "name": f"Call Spread ${K1:g}/${K2:g}",
                "strategy_type": "Call Debit Spread",
                "legs": legs,
                "expiration": exp,
                "strikes": [K1, K2],
                **metrics,
            })
    return results


def _gen_put_debit_spreads(puts, S0, St, exp, pricing_mode, slippage_pct):
    results = []
    buys = _subsample([p for p in puts if S0 * 0.85 <= p["strike"] <= S0 * 1.15], 10)
    sells = _subsample([p for p in puts if S0 * 0.01 <= p["strike"] <= S0 * 1.15], 12)

    for buy_opt in buys:
        K1 = buy_opt["strike"]
        prem1 = _fill_price(buy_opt, "buy", pricing_mode, slippage_pct)
        for sell_opt in sells:
            K2 = sell_opt["strike"]
            if K2 >= K1:
                continue
            prem2 = _fill_price(sell_opt, "sell", pricing_mode, slippage_pct)
            if prem1 - prem2 <= 0:
                continue

            legs = [
                _make_leg("Put", buy_opt, "buy", exp, prem1),
                _make_leg("Put", sell_opt, "sell", exp, prem2),
            ]
            metrics = _compute_canonical_metrics(legs, S0, St, exp)
            if metrics["payoff_at_target"] <= 0 or metrics["capital_required"] <= 0:
                continue

            results.append({
                "name": f"Put Spread ${K1:g}/${K2:g}",
                "strategy_type": "Put Debit Spread",
                "legs": legs,
                "expiration": exp,
                "strikes": [K1, K2],
                **metrics,
            })
    return results


def _gen_call_credit_spreads(calls, S0, St, exp, pricing_mode, slippage_pct):
    results = []
    sells = _subsample([c for c in calls if S0 * 0.85 <= c["strike"] <= S0 * 2.0], 10)
    buys = _subsample([c for c in calls if c["strike"] >= S0 * 0.85], 12)

    for sell_opt in sells:
        K1 = sell_opt["strike"]
        prem1 = _fill_price(sell_opt, "sell", pricing_mode, slippage_pct)
        for buy_opt in buys:
            K2 = buy_opt["strike"]
            if K2 <= K1:
                continue
            prem2 = _fill_price(buy_opt, "buy", pricing_mode, slippage_pct)
            if prem1 - prem2 <= 0:
                continue

            legs = [
                _make_leg("Call", sell_opt, "sell", exp, prem1),
                _make_leg("Call", buy_opt, "buy", exp, prem2),
            ]
            metrics = _compute_canonical_metrics(legs, S0, St, exp)
            if metrics["payoff_at_target"] <= 0 or metrics["capital_required"] <= 0:
                continue

            results.append({
                "name": f"Call Credit ${K1:g}/${K2:g}",
                "strategy_type": "Call Credit Spread",
                "legs": legs,
                "expiration": exp,
                "strikes": [K1, K2],
                **metrics,
            })
    return results


def _gen_put_credit_spreads(puts, S0, St, exp, pricing_mode, slippage_pct):
    results = []
    sells = _subsample([p for p in puts if S0 * 0.01 <= p["strike"] <= S0 * 1.10], 10)
    buys = _subsample([p for p in puts if p["strike"] <= S0 * 1.10], 12)

    for sell_opt in sells:
        K1 = sell_opt["strike"]
        prem1 = _fill_price(sell_opt, "sell", pricing_mode, slippage_pct)
        for buy_opt in buys:
            K2 = buy_opt["strike"]
            if K2 >= K1:
                continue
            prem2 = _fill_price(buy_opt, "buy", pricing_mode, slippage_pct)
            if prem1 - prem2 <= 0:
                continue

            legs = [
                _make_leg("Put", sell_opt, "sell", exp, prem1),
                _make_leg("Put", buy_opt, "buy", exp, prem2),
            ]
            metrics = _compute_canonical_metrics(legs, S0, St, exp)
            if metrics["payoff_at_target"] <= 0 or metrics["capital_required"] <= 0:
                continue

            results.append({
                "name": f"Put Credit ${K2:g}/${K1:g}",
                "strategy_type": "Put Credit Spread",
                "legs": legs,
                "expiration": exp,
                "strikes": [K2, K1],
                **metrics,
            })
    return results


def _gen_iron_condors(calls, puts, S0, St, exp, pricing_mode, slippage_pct):
    results = []
    for wing_pct in [0.03, 0.05, 0.08, 0.12, 0.20, 0.30]:
        sp = _nearest(puts, S0 * (1 - wing_pct))
        bp = _nearest(puts, S0 * (1 - wing_pct - 0.03))
        sc = _nearest(calls, S0 * (1 + wing_pct))
        bc = _nearest(calls, S0 * (1 + wing_pct + 0.03))

        if sp["strike"] <= bp["strike"] or bc["strike"] <= sc["strike"]:
            continue

        prem_bp = _fill_price(bp, "buy", pricing_mode, slippage_pct)
        prem_sp = _fill_price(sp, "sell", pricing_mode, slippage_pct)
        prem_sc = _fill_price(sc, "sell", pricing_mode, slippage_pct)
        prem_bc = _fill_price(bc, "buy", pricing_mode, slippage_pct)

        net_credit = (prem_sp + prem_sc) - (prem_bp + prem_bc)
        if net_credit <= 0:
            continue

        legs = [
            _make_leg("Put", bp, "buy", exp, prem_bp),
            _make_leg("Put", sp, "sell", exp, prem_sp),
            _make_leg("Call", sc, "sell", exp, prem_sc),
            _make_leg("Call", bc, "buy", exp, prem_bc),
        ]
        metrics = _compute_canonical_metrics(legs, S0, St, exp)
        if metrics["payoff_at_target"] <= 0 or metrics["capital_required"] <= 0:
            continue

        label = f"{wing_pct * 100:.0f}%"
        results.append({
            "name": f"Iron Condor ({label} wings)",
            "strategy_type": "Iron Condor",
            "legs": legs,
            "expiration": exp,
            "strikes": [bp["strike"], sp["strike"], sc["strike"], bc["strike"]],
            **metrics,
        })
    return results


# ── Helpers ──────────────────────────────────────────────────


def _get_mid(opt):
    """Get mid price from chain option dict. Uses canonical mark_price."""
    return mark_price(opt.get("bid"), opt.get("ask"), opt.get("last_price")) or 0


def _fill_price(opt, action, pricing_mode="mid", slippage_pct=0.0):
    """Get execution-realistic fill price for a leg."""
    price = entry_fill_price(
        action=action,
        bid=opt.get("bid"),
        ask=opt.get("ask"),
        last=opt.get("last_price"),
        mode=pricing_mode,
        slippage_pct=slippage_pct,
    )
    return price or 0


def _make_leg(opt_type, opt, action, exp, fill_prem=None):
    prem = fill_prem if fill_prem is not None else _get_mid(opt)
    return {
        "type": opt_type,
        "strike": opt["strike"],
        "action": action,
        "quantity": 1,
        "premium": prem,
        "bid": opt.get("bid"),
        "ask": opt.get("ask"),
        "iv": opt.get("implied_volatility"),
        "expiration": exp,
    }


def _nearest(options, target):
    return min(options, key=lambda o: abs(o["strike"] - target))


def _liquid(opt):
    """Filter for minimum liquidity. Rejects clearly illiquid options."""
    bid = opt.get("bid") or 0
    ask = opt.get("ask") or 0
    oi = opt.get("open_interest") or 0
    vol = opt.get("volume") or 0

    # Must have positive bid or reasonable OI
    if bid <= 0 and oi < 25 and vol < 10:
        return False

    # Reject if spread is too wide (>20%)
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        if mid > 0:
            spread_pct = (ask - bid) / mid
            if spread_pct > 0.20:
                return False

    return True


def _parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def _subsample(items, max_n=10):
    """Evenly subsample a list if it exceeds max_n."""
    if len(items) <= max_n:
        return items
    step = len(items) / max_n
    return [items[int(i * step)] for i in range(max_n)]
