"""Strategy Recommender – rebuilt per recommendation_engine.md spec.

Deterministic engine that evaluates option strategies based on user-defined
target price and date, computes payoff at target at expiration, and ranks
by capital efficiency (risk-reward = payoff_at_target / capital_required).
"""

from __future__ import annotations

import math
from datetime import datetime, date
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from data_provider.base import DataProvider


# ── API ─────────────────────────────────────────────────────


class RecommendRequest(BaseModel):
    ticker: str
    target_price: float
    target_date: str  # YYYY-MM-DD


def create_recommender_routes(provider: DataProvider) -> APIRouter:
    router = APIRouter(prefix="/api/recommend", tags=["recommender"])

    @router.post("")
    def recommend(req: RecommendRequest):
        try:
            results, direction, expiration_used = _recommend(
                provider, req.ticker, req.target_price, req.target_date,
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


def _recommend(provider, ticker, target_price, target_date):
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
        [c for c in chain.get("calls", []) if _liquid(c) and _mid(c) > 0],
        key=lambda c: c["strike"],
    )
    puts = sorted(
        [p for p in chain.get("puts", []) if _liquid(p) and _mid(p) > 0],
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
            candidates += _gen_long_calls(calls, current_price, target_price, best_exp)
            candidates += _gen_call_debit_spreads(calls, current_price, target_price, best_exp)
        if puts:
            candidates += _gen_put_credit_spreads(puts, current_price, target_price, best_exp)
    elif direction == "bearish":
        if puts:
            candidates += _gen_long_puts(puts, current_price, target_price, best_exp)
            candidates += _gen_put_debit_spreads(puts, current_price, target_price, best_exp)
        if calls:
            candidates += _gen_call_credit_spreads(calls, current_price, target_price, best_exp)
    else:  # neutral
        if calls and puts:
            candidates += _gen_iron_condors(calls, puts, current_price, target_price, best_exp)

    # ── 5. Filter: payoff must be > 0 and capital must be > 0 ──
    valid = [c for c in candidates if c["payoff_at_target"] > 0 and c["capital_required"] > 0]

    # ── 6. Sort by risk-reward descending ──
    valid.sort(key=lambda x: x["risk_reward"], reverse=True)

    # ── 7. Return top 5 with payoff curves ──
    top = valid[:5]
    for item in top:
        item["curve"] = _payoff_curve(item["legs"], current_price, target_price)
        item["current_price"] = current_price
        item["ticker"] = ticker

    return top, direction, best_exp


# ── Strategy Generators ──────────────────────────────────────


def _gen_long_calls(calls, S0, St, exp):
    """Long Call: evaluate strikes from ATM to moderately OTM."""
    results = []
    for opt in calls:
        K = opt["strike"]
        if K < S0 * 0.85 or K > S0 * 2.0:
            continue
        prem = _mid(opt)
        # Payoff = max(St - K, 0) - Premium
        payoff_ps = max(St - K, 0) - prem
        capital_ps = prem
        if payoff_ps <= 0 or capital_ps <= 0:
            continue

        payoff = round(payoff_ps * 100, 2)
        capital = round(capital_ps * 100, 2)
        rr = round(payoff / capital, 2)

        results.append({
            "name": f"Long ${K:g} Call",
            "strategy_type": "Long Call",
            "legs": [_make_leg("Call", opt, "buy", exp)],
            "expiration": exp,
            "strikes": [K],
            "net_premium": round(-capital, 2),
            "capital_required": capital,
            "payoff_at_target": payoff,
            "risk_reward": rr,
            "max_profit": None,  # Unlimited — NEVER capped
            "max_loss": round(-capital, 2),
            "breakevens": [round(K + prem, 2)],
        })
    return results


def _gen_long_puts(puts, S0, St, exp):
    """Long Put: evaluate strikes from ATM to moderately OTM."""
    results = []
    for opt in puts:
        K = opt["strike"]
        if K < S0 * 0.01 or K > S0 * 1.15:
            continue
        prem = _mid(opt)
        # Payoff = max(K - St, 0) - Premium
        payoff_ps = max(K - St, 0) - prem
        capital_ps = prem
        if payoff_ps <= 0 or capital_ps <= 0:
            continue

        payoff = round(payoff_ps * 100, 2)
        capital = round(capital_ps * 100, 2)
        max_profit_ps = K - prem  # stock goes to 0
        rr = round(payoff / capital, 2)

        results.append({
            "name": f"Long ${K:g} Put",
            "strategy_type": "Long Put",
            "legs": [_make_leg("Put", opt, "buy", exp)],
            "expiration": exp,
            "strikes": [K],
            "net_premium": round(-capital, 2),
            "capital_required": capital,
            "payoff_at_target": payoff,
            "risk_reward": rr,
            "max_profit": round(max_profit_ps * 100, 2),
            "max_loss": round(-capital, 2),
            "breakevens": [round(K - prem, 2)],
        })
    return results


def _gen_call_debit_spreads(calls, S0, St, exp):
    """Call Debit Spread (bullish): buy lower K1, sell higher K2.

    K1 near ATM, K2 near/above target.
    """
    results = []
    buys = _subsample([c for c in calls if S0 * 0.85 <= c["strike"] <= S0 * 1.15], 10)
    sells = _subsample([c for c in calls if S0 * 0.85 <= c["strike"] <= S0 * 2.0], 12)

    for buy_opt in buys:
        K1 = buy_opt["strike"]
        prem1 = _mid(buy_opt)
        for sell_opt in sells:
            K2 = sell_opt["strike"]
            if K2 <= K1:
                continue
            prem2 = _mid(sell_opt)
            net_debit = prem1 - prem2
            if net_debit <= 0:
                continue

            width = K2 - K1
            # SpreadValue = min(max(St - K1, 0), Width)
            spread_val = min(max(St - K1, 0), width)
            payoff_ps = spread_val - net_debit
            if payoff_ps <= 0:
                continue

            payoff = round(payoff_ps * 100, 2)
            capital = round(net_debit * 100, 2)
            rr = round(payoff / capital, 2)
            max_profit = round((width - net_debit) * 100, 2)

            results.append({
                "name": f"Call Spread ${K1:g}/${K2:g}",
                "strategy_type": "Call Debit Spread",
                "legs": [
                    _make_leg("Call", buy_opt, "buy", exp),
                    _make_leg("Call", sell_opt, "sell", exp),
                ],
                "expiration": exp,
                "strikes": [K1, K2],
                "net_premium": round(-capital, 2),
                "capital_required": capital,
                "payoff_at_target": payoff,
                "risk_reward": rr,
                "max_profit": max_profit,
                "max_loss": round(-capital, 2),
                "breakevens": [round(K1 + net_debit, 2)],
            })
    return results


def _gen_put_debit_spreads(puts, S0, St, exp):
    """Put Debit Spread (bearish): buy higher K1, sell lower K2.

    K1 near ATM, K2 near/below target.
    """
    results = []
    buys = _subsample([p for p in puts if S0 * 0.85 <= p["strike"] <= S0 * 1.15], 10)
    sells = _subsample([p for p in puts if S0 * 0.01 <= p["strike"] <= S0 * 1.15], 12)

    for buy_opt in buys:
        K1 = buy_opt["strike"]
        prem1 = _mid(buy_opt)
        for sell_opt in sells:
            K2 = sell_opt["strike"]
            if K2 >= K1:
                continue
            prem2 = _mid(sell_opt)
            net_debit = prem1 - prem2
            if net_debit <= 0:
                continue

            width = K1 - K2
            # SpreadValue = min(max(K1 - St, 0), Width)
            spread_val = min(max(K1 - St, 0), width)
            payoff_ps = spread_val - net_debit
            if payoff_ps <= 0:
                continue

            payoff = round(payoff_ps * 100, 2)
            capital = round(net_debit * 100, 2)
            rr = round(payoff / capital, 2)
            max_profit = round((width - net_debit) * 100, 2)

            results.append({
                "name": f"Put Spread ${K1:g}/${K2:g}",
                "strategy_type": "Put Debit Spread",
                "legs": [
                    _make_leg("Put", buy_opt, "buy", exp),
                    _make_leg("Put", sell_opt, "sell", exp),
                ],
                "expiration": exp,
                "strikes": [K1, K2],
                "net_premium": round(-capital, 2),
                "capital_required": capital,
                "payoff_at_target": payoff,
                "risk_reward": rr,
                "max_profit": max_profit,
                "max_loss": round(-capital, 2),
                "breakevens": [round(K1 - net_debit, 2)],
            })
    return results


def _gen_call_credit_spreads(calls, S0, St, exp):
    """Call Credit Spread (bearish): sell lower K1, buy higher K2.

    Sell strike near/just above target (which is below current for bearish).
    """
    results = []
    sells = _subsample([c for c in calls if S0 * 0.85 <= c["strike"] <= S0 * 2.0], 10)
    buys = _subsample([c for c in calls if c["strike"] >= S0 * 0.85], 12)

    for sell_opt in sells:
        K1 = sell_opt["strike"]
        prem1 = _mid(sell_opt)
        for buy_opt in buys:
            K2 = buy_opt["strike"]
            if K2 <= K1:
                continue
            prem2 = _mid(buy_opt)
            net_credit = prem1 - prem2
            if net_credit <= 0:
                continue

            width = K2 - K1
            max_loss_ps = width - net_credit
            if max_loss_ps <= 0:
                continue

            # Payoff = NetCredit - min(max(St - K1, 0), Width)
            intrinsic_loss = max(St - K1, 0)
            actual_loss = min(intrinsic_loss, width)
            payoff_ps = net_credit - actual_loss
            if payoff_ps <= 0:
                continue

            payoff = round(payoff_ps * 100, 2)
            capital = round(max_loss_ps * 100, 2)
            rr = round(payoff / capital, 2)

            results.append({
                "name": f"Call Credit ${K1:g}/${K2:g}",
                "strategy_type": "Call Credit Spread",
                "legs": [
                    _make_leg("Call", sell_opt, "sell", exp),
                    _make_leg("Call", buy_opt, "buy", exp),
                ],
                "expiration": exp,
                "strikes": [K1, K2],
                "net_premium": round(net_credit * 100, 2),
                "capital_required": capital,
                "payoff_at_target": payoff,
                "risk_reward": rr,
                "max_profit": round(net_credit * 100, 2),
                "max_loss": round(-capital, 2),
                "breakevens": [round(K1 + net_credit, 2)],
            })
    return results


def _gen_put_credit_spreads(puts, S0, St, exp):
    """Put Credit Spread (bullish): sell higher K1, buy lower K2.

    Sell strike just below current price.
    """
    results = []
    sells = _subsample([p for p in puts if S0 * 0.01 <= p["strike"] <= S0 * 1.10], 10)
    buys = _subsample([p for p in puts if p["strike"] <= S0 * 1.10], 12)

    for sell_opt in sells:
        K1 = sell_opt["strike"]
        prem1 = _mid(sell_opt)
        for buy_opt in buys:
            K2 = buy_opt["strike"]
            if K2 >= K1:
                continue
            prem2 = _mid(buy_opt)
            net_credit = prem1 - prem2
            if net_credit <= 0:
                continue

            width = K1 - K2
            max_loss_ps = width - net_credit
            if max_loss_ps <= 0:
                continue

            # Payoff = NetCredit - min(max(K1 - St, 0), Width)
            intrinsic_loss = max(K1 - St, 0)
            actual_loss = min(intrinsic_loss, width)
            payoff_ps = net_credit - actual_loss
            if payoff_ps <= 0:
                continue

            payoff = round(payoff_ps * 100, 2)
            capital = round(max_loss_ps * 100, 2)
            rr = round(payoff / capital, 2)

            results.append({
                "name": f"Put Credit ${K2:g}/${K1:g}",
                "strategy_type": "Put Credit Spread",
                "legs": [
                    _make_leg("Put", sell_opt, "sell", exp),
                    _make_leg("Put", buy_opt, "buy", exp),
                ],
                "expiration": exp,
                "strikes": [K2, K1],
                "net_premium": round(net_credit * 100, 2),
                "capital_required": capital,
                "payoff_at_target": payoff,
                "risk_reward": rr,
                "max_profit": round(net_credit * 100, 2),
                "max_loss": round(-capital, 2),
                "breakevens": [round(K1 - net_credit, 2)],
            })
    return results


def _gen_iron_condors(calls, puts, S0, St, exp):
    """Iron Condor (neutral): sell put spread below + sell call spread above."""
    results = []
    for wing_pct in [0.03, 0.05, 0.08, 0.12, 0.20, 0.30]:
        sp = _nearest(puts, S0 * (1 - wing_pct))
        bp = _nearest(puts, S0 * (1 - wing_pct - 0.03))
        sc = _nearest(calls, S0 * (1 + wing_pct))
        bc = _nearest(calls, S0 * (1 + wing_pct + 0.03))

        if sp["strike"] <= bp["strike"] or bc["strike"] <= sc["strike"]:
            continue

        net_credit = (_mid(sp) + _mid(sc)) - (_mid(bp) + _mid(bc))
        if net_credit <= 0:
            continue

        put_width = sp["strike"] - bp["strike"]
        call_width = bc["strike"] - sc["strike"]
        wider = max(put_width, call_width)
        max_loss_ps = wider - net_credit
        if max_loss_ps <= 0:
            continue

        # Payoff at St
        put_loss = min(max(sp["strike"] - St, 0), put_width)
        call_loss = min(max(St - sc["strike"], 0), call_width)
        payoff_ps = net_credit - put_loss - call_loss
        if payoff_ps <= 0:
            continue

        payoff = round(payoff_ps * 100, 2)
        capital = round(max_loss_ps * 100, 2)
        rr = round(payoff / capital, 2)
        label = f"{wing_pct * 100:.0f}%"

        results.append({
            "name": f"Iron Condor ({label} wings)",
            "strategy_type": "Iron Condor",
            "legs": [
                _make_leg("Put", bp, "buy", exp),
                _make_leg("Put", sp, "sell", exp),
                _make_leg("Call", sc, "sell", exp),
                _make_leg("Call", bc, "buy", exp),
            ],
            "expiration": exp,
            "strikes": [bp["strike"], sp["strike"], sc["strike"], bc["strike"]],
            "net_premium": round(net_credit * 100, 2),
            "capital_required": capital,
            "payoff_at_target": payoff,
            "risk_reward": rr,
            "max_profit": round(net_credit * 100, 2),
            "max_loss": round(-capital, 2),
            "breakevens": [
                round(sp["strike"] - net_credit, 2),
                round(sc["strike"] + net_credit, 2),
            ],
        })
    return results


# ── Helpers ──────────────────────────────────────────────────


def _leg_pl(leg, stock_price):
    """P&L for one leg at expiry (per contract, ×100 multiplier)."""
    strike = leg["strike"]
    prem = leg["premium"]
    qty = leg["quantity"]
    d = 1 if leg["action"] == "buy" else -1
    intr = (
        max(0, stock_price - strike) if leg["type"] == "Call"
        else max(0, strike - stock_price)
    )
    return d * (intr - prem) * 100 * qty


def _payoff_curve(legs, current_price, target_price=None):
    """Generate 50-point payoff curve for inline chart."""
    strikes = [l["strike"] for l in legs]
    min_s = min(strikes)
    max_s = max(strikes)
    spread = max_s - min_s if max_s > min_s else current_price * 0.1
    padding = max(spread * 1.5, current_price * 0.15)
    lo = max(0, min(min_s, current_price) - padding)
    hi = max(max_s, current_price) + padding

    if target_price is not None:
        tp_padding = abs(target_price - current_price) * 0.15
        lo = max(0, min(lo, target_price - tp_padding))
        hi = max(hi, target_price + tp_padding)

    n = 50
    step = (hi - lo) / n
    points = []
    for i in range(n + 1):
        p = lo + i * step
        pl = sum(_leg_pl(leg, p) for leg in legs)
        points.append({"price": round(p, 2), "pl": round(pl, 2)})
    return points


def _make_leg(opt_type, opt, action, exp):
    return {
        "type": opt_type,
        "strike": opt["strike"],
        "action": action,
        "quantity": 1,
        "premium": _mid(opt),
        "bid": opt.get("bid"),
        "ask": opt.get("ask"),
        "iv": opt.get("implied_volatility"),
        "expiration": exp,
    }


def _mid(opt):
    bid = opt.get("bid") or 0
    ask = opt.get("ask") or 0
    if bid > 0 and ask > 0:
        return round((bid + ask) / 2, 2)
    return opt.get("last_price") or 0


def _nearest(options, target):
    return min(options, key=lambda o: abs(o["strike"] - target))


def _liquid(opt):
    return (opt.get("bid") or 0) > 0 or (opt.get("open_interest") or 0) > 10


def _parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def _subsample(items, max_n=10):
    """Evenly subsample a list if it exceeds max_n."""
    if len(items) <= max_n:
        return items
    step = len(items) / max_n
    return [items[int(i * step)] for i in range(max_n)]
