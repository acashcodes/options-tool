"""Portfolio enrichment: live pricing, Greeks, metrics, sector data."""

from __future__ import annotations

import math
from datetime import datetime, date
from typing import Any, Optional

from models import Position, AssetType
from greeks import compute_greeks


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
    long_exposure = 0.0
    short_exposure = 0.0
    port_delta = 0.0
    port_gamma = 0.0
    port_theta = 0.0
    port_vega = 0.0
    beta_delta_sum = 0.0

    for pos in positions:
        ticker = pos.ticker.upper()
        quote = quotes.get(ticker, {})
        price = quote.get("price")
        sector = quote.get("sector")
        beta = quote.get("beta")

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
                ep["market_value"] = round(mv, 2)
                ep["cost_basis"] = round(cb, 2)
                ep["pnl"] = round(mv - cb, 2)
                ep["pnl_percent"] = round(((mv - cb) / abs(cb)) * 100, 2) if cb != 0 else None
                # Day P&L = qty * (price - previous_close)
                prev_close = quote.get("previous_close")
                if prev_close is not None:
                    day_pnl = pos.quantity * (price - prev_close)
                    ep["day_pnl"] = round(day_pnl, 2)
                    total_day_pnl += day_pnl
                # Stock delta: per-unit is always 1.0, dollar delta = qty * price
                ep["delta_per_unit"] = 1.0
                pos_delta = pos.quantity * price
                ep["delta"] = round(pos_delta, 2)
                port_delta += pos_delta
                if beta is not None:
                    beta_delta_sum += pos_delta * beta
                total_mv += mv
                total_cost += cb
                gross_exposure += abs(mv)
                net_exposure += mv
                if mv >= 0:
                    long_exposure += mv
                else:
                    short_exposure += abs(mv)
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
                # Use live option price if available, fall back to avg_cost
                opt_px = option_price if option_price is not None else pos.avg_cost
                if opt_px is not None:
                    mv = pos.quantity * multiplier * opt_px
                    cb = pos.quantity * multiplier * pos.avg_cost
                    ep["current_price"] = opt_px
                    ep["market_value"] = round(mv, 2)
                    ep["cost_basis"] = round(cb, 2)
                    ep["pnl"] = round(mv - cb, 2)
                    ep["pnl_percent"] = round(((mv - cb) / abs(cb)) * 100, 2) if cb != 0 else None
                    # Day P&L for options: change in option price × qty × 100
                    if option_price is not None:
                        ep["day_pnl"] = round((option_price - pos.avg_cost) * pos.quantity * multiplier, 2)
                        total_day_pnl += ep["day_pnl"]
                    total_mv += mv
                    total_cost += cb
                    gross_exposure += abs(mv)
                    # Puts provide short exposure, calls provide long exposure
                    if pos.asset_type == AssetType.PUT:
                        net_exposure -= abs(mv)
                        short_exposure += abs(mv)
                    else:
                        net_exposure += mv
                        if mv >= 0:
                            long_exposure += mv
                        else:
                            short_exposure += abs(mv)
                if iv is not None and iv > 0:
                    ep["iv"] = round(iv * 100, 2)  # Store as percentage
                    t_years = _time_to_expiry(pos.expiration)
                    if t_years > 0:
                        greeks = compute_greeks(
                            S=price, K=pos.strike, t=t_years,
                            r=0.045, sigma=iv,
                            option_type="call" if pos.asset_type == AssetType.CALL else "put",
                        )
                        if greeks.get("delta") is not None:
                            ep["delta_per_unit"] = round(greeks["delta"], 4)
                            pos_delta = greeks["delta"] * pos.quantity * multiplier * price
                            ep["delta"] = round(pos_delta, 2)
                            port_delta += pos_delta
                            if beta is not None:
                                beta_delta_sum += pos_delta * beta
                        if greeks.get("gamma") is not None:
                            pos_gamma = greeks["gamma"] * pos.quantity * multiplier
                            ep["gamma"] = round(pos_gamma, 4)
                            port_gamma += pos_gamma
                        if greeks.get("theta") is not None:
                            pos_theta = greeks["theta"] * pos.quantity * multiplier
                            ep["theta"] = round(pos_theta, 2)
                            port_theta += pos_theta
                        if greeks.get("vega") is not None:
                            pos_vega = greeks["vega"] * pos.quantity * multiplier
                            ep["vega"] = round(pos_vega, 2)
                            port_vega += pos_vega

        enriched_positions.append(ep)

    # Compute weights
    for ep in enriched_positions:
        if ep["market_value"] is not None and total_mv != 0:
            ep["weight"] = round((abs(ep["market_value"]) / abs(total_mv)) * 100, 2)

    # Beta-weighted delta (normalised to SPY)
    spy_price = None
    beta_weighted_delta = None
    try:
        spy_quote = provider.get_quote("SPY")
        spy_price = spy_quote.get("price")
        if spy_price and spy_price > 0:
            beta_weighted_delta = round(beta_delta_sum / spy_price, 2)
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
    # Convert to percentage
    total_abs_mv = sum(sector_breakdown.values())
    if total_abs_mv > 0:
        sector_breakdown = {k: round((v / total_abs_mv) * 100, 2) for k, v in sector_breakdown.items()}

    # Concentration (aggregate by ticker, then top 10)
    ticker_agg: dict[str, dict] = {}
    for ep in enriched_positions:
        t = ep["ticker"]
        if t not in ticker_agg:
            ticker_agg[t] = {"ticker": t, "weight": 0, "market_value": 0}
        ticker_agg[t]["weight"] += ep.get("weight") or 0
        ticker_agg[t]["market_value"] += ep.get("market_value") or 0
    concentration = sorted(
        ticker_agg.values(),
        key=lambda x: abs(x["market_value"]),
        reverse=True,
    )[:10]

    # Compute portfolio Sharpe ratio from weighted historical returns
    sharpe_ratio = _compute_portfolio_sharpe(enriched_positions, total_mv, provider)

    pnl = total_mv - total_cost
    day_pnl_pct = round((total_day_pnl / (total_mv - total_day_pnl)) * 100, 2) if (total_mv - total_day_pnl) != 0 and total_day_pnl != 0 else None
    metrics = {
        "total_market_value": round(total_mv, 2),
        "total_cost_basis": round(total_cost, 2),
        "total_pnl": round(pnl, 2),
        "total_pnl_percent": round((pnl / abs(total_cost)) * 100, 2) if total_cost != 0 else None,
        "day_pnl": round(total_day_pnl, 2),
        "day_pnl_percent": day_pnl_pct,
        "gross_exposure": round(gross_exposure, 2),
        "net_exposure": round(net_exposure, 2),
        "long_exposure": round(long_exposure, 2),
        "short_exposure": round(short_exposure, 2),
        "pct_net_long": round((long_exposure / gross_exposure) * 100, 2) if gross_exposure > 0 else None,
        "pct_net_short": round((short_exposure / gross_exposure) * 100, 2) if gross_exposure > 0 else None,
        "leverage_ratio": round(gross_exposure / abs(net_exposure), 2) if net_exposure != 0 else None,
        "position_count": len(positions),
        "greeks": {
            "delta": round(port_delta, 2),
            "gamma": round(port_gamma, 4),
            "theta": round(port_theta, 2),
            "vega": round(port_vega, 2),
            "beta_weighted_delta": beta_weighted_delta,
        },
        "sharpe_ratio": sharpe_ratio,
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
        # Fallback to ATM IV from quote
        atm_iv = quote.get("current_iv")
        return atm_iv / 100 if atm_iv else None
    side = "calls" if asset_type == AssetType.CALL else "puts"
    for opt in chain.get(side, []):
        if abs(opt.get("strike", 0) - strike) < 0.01:
            iv_pct = opt.get("implied_volatility")
            if iv_pct is not None:
                return iv_pct / 100  # Convert from percentage to decimal
    # Fallback to ATM IV
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


def _time_to_expiry(expiration: str) -> float:
    try:
        exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        today = date.today()
        days = (exp_date - today).days
        return max(days, 0) / 365.0
    except Exception:
        return 0.0


def _compute_risk_flags(positions: list[dict]) -> list[str]:
    flags = []

    # Ticker-level concentration > 25% (aggregate all positions for same ticker)
    ticker_weights: dict[str, float] = {}
    for ep in positions:
        t = ep["ticker"]
        ticker_weights[t] = ticker_weights.get(t, 0) + (ep.get("weight") or 0)
    for t, w in ticker_weights.items():
        if w > 25:
            flags.append(f"{t} is {w:.0f}% of portfolio (>25%)")

    # Sector concentration > 40%
    sector_weights: dict[str, float] = {}
    for ep in positions:
        s = ep.get("sector") or "Unknown"
        sector_weights[s] = sector_weights.get(s, 0) + (ep.get("weight") or 0)
    for s, w in sector_weights.items():
        if w > 40 and s != "Unknown":
            flags.append(f"{s} sector is {w:.0f}% of portfolio (>40%)")

    # 3+ holdings in same sector
    sector_counts: dict[str, int] = {}
    for ep in positions:
        s = ep.get("sector") or "Unknown"
        sector_counts[s] = sector_counts.get(s, 0) + 1
    for s, c in sector_counts.items():
        if c >= 3 and s != "Unknown":
            flags.append(f"{c} positions in {s} sector")

    return flags


def _compute_portfolio_sharpe(
    enriched_positions: list[dict], total_mv: float, provider: Any
) -> Optional[float]:
    """Compute annualised Sharpe ratio from 60-day weighted portfolio returns.

    Uses each stock position's historical daily returns, weighted by current
    portfolio weight.  Options are skipped (their P&L is path-dependent and
    not captured well by underlying returns alone).
    """
    if total_mv <= 0:
        return None

    # Collect weights for stock positions only
    ticker_weights: dict[str, float] = {}
    for ep in enriched_positions:
        if ep["asset_type"] == "stock" and ep.get("market_value"):
            t = ep["ticker"]
            ticker_weights[t] = ticker_weights.get(t, 0) + ep["market_value"]
    stock_mv = sum(ticker_weights.values())
    if stock_mv <= 0:
        return None
    # Normalise weights so they sum to 1
    for t in ticker_weights:
        ticker_weights[t] /= stock_mv

    # Fetch 90-day history for each ticker (gives us ~60 trading days)
    histories: dict[str, list[float]] = {}
    for t in ticker_weights:
        try:
            hist = provider.get_history(t, period="3mo", interval="1d")
            closes = [bar["close"] for bar in hist if bar.get("close")]
            if len(closes) >= 20:
                # daily returns
                rets = [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes))]
                histories[t] = rets
        except Exception:
            continue

    if not histories:
        return None

    # Use the shortest common length
    min_len = min(len(r) for r in histories.values())
    if min_len < 15:
        return None

    # Compute portfolio daily returns
    import statistics
    port_returns = []
    for i in range(min_len):
        day_ret = sum(
            ticker_weights[t] * histories[t][-(min_len - i)]
            for t in histories
        )
        port_returns.append(day_ret)

    mean_ret = statistics.mean(port_returns)
    std_ret = statistics.stdev(port_returns) if len(port_returns) > 1 else 0
    if std_ret <= 0:
        return None

    # Annualise: Sharpe = (mean_daily / std_daily) * sqrt(252)
    sharpe = (mean_ret / std_ret) * math.sqrt(252)
    return round(sharpe, 2)
