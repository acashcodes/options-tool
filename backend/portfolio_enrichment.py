"""Portfolio enrichment: live pricing, Greeks, metrics, sector data.

Uses time_utils for accurate time-to-expiry, BSM with dividend yield,
full-precision floats (rounding only at final output), and SQLite mark
history for correct day P&L computation.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from models import Position, AssetType
from greeks import compute_greeks
import time_utils
from formatting import money, pct, greek
from repositories.marks_repo import record_today_mark, get_prior_mark


def enrich_portfolio(positions: list[Position], provider: Any) -> dict:
    """Enrich all positions with live data and compute portfolio-level metrics."""

    # Batch-fetch quotes for all unique tickers
    tickers = list({p.ticker.upper() for p in positions})
    quotes = {}
    for t in tickers:
        try:
            quotes[t] = provider.get_quote(t)
        except Exception:
            quotes[t] = {}

    # Cache for option chains (ticker+expiry -> chain)
    chain_cache: dict[str, dict] = {}

    enriched_positions = []
    total_mv = 0.0
    total_cost = 0.0
    total_day_pnl = 0.0
    gross_exposure = 0.0
    net_exposure = 0.0
    port_delta = 0.0
    port_gamma = 0.0
    port_theta = 0.0
    port_vega = 0.0
    beta_delta_sum = 0.0

    from assumptions import default_risk_free_rate
    risk_free_rate = default_risk_free_rate(provider)

    for pos in positions:
        ticker = pos.ticker.upper()
        quote = quotes.get(ticker, {})
        price = quote.get("price")
        sector = quote.get("sector")
        beta = quote.get("beta")
        q = quote.get("dividend_yield") or 0.0

        ep = {
            "id": pos.id,
            "ticker": ticker,
            "asset_type": pos.asset_type,
            "quantity": pos.quantity,
            "avg_cost": pos.avg_cost,
            "strike": pos.strike,
            "expiration": pos.expiration,
            "current_price": price,
            "sector": sector,
            "beta": beta,
            "market_value": None,
            "cost_basis": None,
            "pnl": None,
            "pnl_percent": None,
            "day_pnl": None,
            "day_pnl_unavailable": False,
            "delta": None,
            "delta_per_unit": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "iv": None,
            "weight": None,
        }

        if pos.asset_type == AssetType.STOCK:
            if price is not None:
                mv = pos.quantity * price
                cb = pos.quantity * pos.avg_cost
                ep["market_value"] = mv
                ep["cost_basis"] = cb
                ep["pnl"] = mv - cb
                ep["pnl_percent"] = ((mv - cb) / abs(cb)) * 100 if cb != 0 else None
                # Record today's mark for stock
                record_today_mark(ticker, "stock", price, "live")
                # Day P&L: use prior mark from marks table (correct method)
                prior_mark = get_prior_mark(ticker, "stock")
                if prior_mark is not None:
                    day_pnl = pos.quantity * (price - prior_mark)
                    ep["day_pnl"] = day_pnl
                    total_day_pnl += day_pnl
                else:
                    # Fallback to previous_close from quote if no prior mark
                    prev_close = quote.get("previous_close")
                    if prev_close is not None:
                        day_pnl = pos.quantity * (price - prev_close)
                        ep["day_pnl"] = day_pnl
                        total_day_pnl += day_pnl
                # Stock delta: per-unit is always 1.0, dollar delta = qty * price
                ep["delta_per_unit"] = 1.0
                pos_delta = pos.quantity * price
                ep["delta"] = pos_delta
                port_delta += pos_delta
                if beta is not None:
                    beta_delta_sum += pos_delta * beta
                total_mv += mv
                total_cost += cb
                gross_exposure += abs(mv)
                net_exposure += mv
        else:
            # Option position
            if price is not None and pos.strike and pos.expiration:
                option_price = _get_option_price(
                    provider, ticker, pos.expiration, pos.strike,
                    pos.asset_type, chain_cache
                )
                iv = _get_option_iv(
                    provider, ticker, pos.expiration, pos.strike,
                    pos.asset_type, chain_cache, quote
                )

                multiplier = 100
                opt_px = option_price if option_price is not None else pos.avg_cost
                if opt_px is not None:
                    mv = pos.quantity * multiplier * opt_px
                    cb = pos.quantity * multiplier * pos.avg_cost
                    ep["current_price"] = opt_px
                    ep["market_value"] = mv
                    ep["cost_basis"] = cb
                    ep["pnl"] = mv - cb
                    ep["pnl_percent"] = ((mv - cb) / abs(cb)) * 100 if cb != 0 else None
                    # Record today's option mark
                    mark_source = "mid" if option_price is not None else "avg_cost"
                    record_today_mark(
                        ticker, pos.asset_type.value, opt_px, mark_source,
                        strike=pos.strike, expiration=pos.expiration,
                    )
                    # Day P&L: use prior mark from marks table
                    prior_opt_mark = get_prior_mark(
                        ticker, pos.asset_type.value,
                        strike=pos.strike, expiration=pos.expiration,
                    )
                    if prior_opt_mark is not None:
                        opt_day_pnl = pos.quantity * multiplier * (opt_px - prior_opt_mark)
                        ep["day_pnl"] = opt_day_pnl
                        ep["day_pnl_unavailable"] = False
                        total_day_pnl += opt_day_pnl
                    else:
                        ep["day_pnl"] = None
                        ep["day_pnl_unavailable"] = True
                    total_mv += mv
                    total_cost += cb
                    gross_exposure += abs(mv)
                    net_exposure += mv

                if iv is not None and iv > 0:
                    ep["iv"] = iv * 100  # Store as percentage
                    t_years = time_utils.year_frac_to(pos.expiration)
                    if t_years > 0:
                        greeks = compute_greeks(
                            S=price, K=pos.strike, t=t_years,
                            r=risk_free_rate, sigma=iv,
                            option_type="call" if pos.asset_type == AssetType.CALL else "put",
                            q=q,
                        )
                        if greeks.get("delta") is not None:
                            ep["delta_per_unit"] = greeks["delta"]
                            pos_delta = greeks["delta"] * pos.quantity * multiplier * price
                            ep["delta"] = pos_delta
                            port_delta += pos_delta
                            if beta is not None:
                                beta_delta_sum += pos_delta * beta
                        if greeks.get("gamma") is not None:
                            pos_gamma = greeks["gamma"] * pos.quantity * multiplier
                            ep["gamma"] = pos_gamma
                            port_gamma += pos_gamma
                        if greeks.get("theta") is not None:
                            pos_theta = greeks["theta"] * pos.quantity * multiplier
                            ep["theta"] = pos_theta
                            port_theta += pos_theta
                        if greeks.get("vega") is not None:
                            pos_vega = greeks["vega"] * pos.quantity * multiplier
                            ep["vega"] = pos_vega
                            port_vega += pos_vega

        # Apply display rounding at the end
        ep["market_value"] = money(ep["market_value"])
        ep["cost_basis"] = money(ep["cost_basis"])
        ep["pnl"] = money(ep["pnl"])
        ep["pnl_percent"] = pct(ep["pnl_percent"])
        ep["day_pnl"] = money(ep["day_pnl"])
        ep["delta"] = money(ep["delta"])
        ep["delta_per_unit"] = greek(ep["delta_per_unit"])
        ep["gamma"] = greek(ep["gamma"])
        ep["theta"] = money(ep["theta"])
        ep["vega"] = money(ep["vega"])
        ep["iv"] = pct(ep["iv"])

        enriched_positions.append(ep)

    # Compute weights
    for ep in enriched_positions:
        if ep["market_value"] is not None and total_mv != 0:
            ep["weight"] = pct((abs(ep["market_value"]) / abs(total_mv)) * 100)

    # Beta-weighted delta (normalised to SPY)
    spy_price = None
    beta_weighted_delta = None
    try:
        spy_quote = provider.get_quote("SPY")
        spy_price = spy_quote.get("price")
        if spy_price and spy_price > 0:
            beta_weighted_delta = money(beta_delta_sum / spy_price)
    except Exception:
        pass

    # Risk flags
    risk_flags = _compute_risk_flags(enriched_positions)

    # Sector breakdown
    sector_breakdown = {}
    for ep in enriched_positions:
        s = ep.get("sector") or "Unknown"
        mv = abs(ep.get("market_value") or 0)
        sector_breakdown[s] = sector_breakdown.get(s, 0) + mv
    total_abs_mv = sum(sector_breakdown.values())
    if total_abs_mv > 0:
        sector_breakdown = {k: pct((v / total_abs_mv) * 100) for k, v in sector_breakdown.items()}

    # Concentration
    concentration = sorted(
        [{"ticker": ep["ticker"], "weight": ep.get("weight") or 0, "market_value": ep.get("market_value") or 0}
         for ep in enriched_positions],
        key=lambda x: abs(x["market_value"]),
        reverse=True,
    )[:10]

    total_pnl = total_mv - total_cost
    day_pnl_pct = pct((total_day_pnl / (total_mv - total_day_pnl)) * 100) if (total_mv - total_day_pnl) != 0 and total_day_pnl != 0 else None
    metrics = {
        "total_market_value": money(total_mv),
        "total_cost_basis": money(total_cost),
        "total_pnl": money(total_pnl),
        "total_pnl_percent": pct((total_pnl / abs(total_cost)) * 100) if total_cost != 0 else None,
        "day_pnl": money(total_day_pnl),
        "day_pnl_percent": day_pnl_pct,
        "gross_exposure": money(gross_exposure),
        "net_exposure": money(net_exposure),
        "leverage_ratio": pct(gross_exposure / abs(net_exposure)) if net_exposure != 0 else None,
        "position_count": len(positions),
        "greeks": {
            "delta": money(port_delta),
            "gamma": greek(port_gamma),
            "theta": money(port_theta),
            "vega": money(port_vega),
            "beta_weighted_delta": beta_weighted_delta,
        },
        "risk_flags": risk_flags,
        "sector_breakdown": sector_breakdown,
        "concentration": concentration,
    }

    return {"positions": enriched_positions, "metrics": metrics}


def _get_option_price(
    provider: Any, ticker: str, expiration: str, strike: float,
    asset_type: AssetType, cache: dict
) -> Optional[float]:
    chain = _fetch_chain(provider, ticker, expiration, cache)
    if chain is None:
        return None
    side = "calls" if asset_type == AssetType.CALL else "puts"
    for opt in chain.get(side, []):
        if abs(opt.get("strike", 0) - strike) < 0.01:
            mid = None
            bid = opt.get("bid")
            ask = opt.get("ask")
            if bid is not None and ask is not None and bid > 0:
                mid = (bid + ask) / 2
            return mid or opt.get("last_price")
    return None


def _get_option_iv(
    provider: Any, ticker: str, expiration: str, strike: float,
    asset_type: AssetType, cache: dict, quote: dict
) -> Optional[float]:
    """Get IV for a specific option. Returns decimal (e.g. 0.30 for 30%)."""
    chain = _fetch_chain(provider, ticker, expiration, cache)
    if chain is None:
        atm_iv = quote.get("current_iv")
        return atm_iv / 100 if atm_iv else None
    side = "calls" if asset_type == AssetType.CALL else "puts"
    for opt in chain.get(side, []):
        if abs(opt.get("strike", 0) - strike) < 0.01:
            iv_pct = opt.get("implied_volatility")
            if iv_pct is not None:
                return iv_pct / 100
    atm_iv = quote.get("current_iv")
    return atm_iv / 100 if atm_iv else None


def _fetch_chain(provider: Any, ticker: str, expiration: str, cache: dict) -> Optional[dict]:
    key = f"{ticker}:{expiration}"
    if key in cache:
        return cache[key]
    try:
        chain = provider.get_options_chain(ticker, expiration)
        cache[key] = chain
        return chain
    except Exception:
        cache[key] = None
        return None


def _compute_risk_flags(positions: list[dict]) -> list[str]:
    flags = []

    for ep in positions:
        w = ep.get("weight") or 0
        if w > 25:
            flags.append(f"{ep['ticker']} is {w:.0f}% of portfolio (>25%)")

    sector_weights: dict[str, float] = {}
    for ep in positions:
        s = ep.get("sector") or "Unknown"
        sector_weights[s] = sector_weights.get(s, 0) + (ep.get("weight") or 0)
    for s, w in sector_weights.items():
        if w > 40 and s != "Unknown":
            flags.append(f"{s} sector is {w:.0f}% of portfolio (>40%)")

    sector_counts: dict[str, int] = {}
    for ep in positions:
        s = ep.get("sector") or "Unknown"
        sector_counts[s] = sector_counts.get(s, 0) + 1
    for s, c in sector_counts.items():
        if c >= 3 and s != "Unknown":
            flags.append(f"{c} positions in {s} sector")

    return flags
