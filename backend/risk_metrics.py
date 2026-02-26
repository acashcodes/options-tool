"""Portfolio risk metrics: correlation, realized beta, stress tests.

Provides correlation matrix, realized beta vs SPY, and stress test
P&L estimates for portfolio-level risk analysis.
"""

from __future__ import annotations

from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


def compute_return_series(provider: Any, tickers: list[str], lookback: str = "6mo") -> dict[str, list[float]]:
    """Fetch daily close returns for each ticker.

    Returns {ticker: [daily_return_1, daily_return_2, ...]} aligned by date.
    """
    import math

    # Fetch history in parallel
    histories: dict[str, list[dict]] = {}

    def fetch(t: str):
        try:
            data = provider.get_history(t, period=lookback, interval="1d")
            return t, data
        except Exception:
            return t, []

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(fetch, t) for t in tickers]
        for fut in as_completed(futures):
            ticker, data = fut.result()
            if data:
                histories[ticker] = data

    if len(histories) < 2:
        return {}

    # Build date-aligned close prices
    date_prices: dict[str, dict[str, float]] = {}
    all_dates: set[str] = set()

    for ticker, data in histories.items():
        for bar in data:
            d = bar.get("date", "")[:10]  # YYYY-MM-DD
            c = bar.get("close")
            if d and c is not None and c > 0:
                if d not in date_prices:
                    date_prices[d] = {}
                date_prices[d][ticker] = c
                all_dates.add(d)

    # Sort dates and compute returns only for dates where ALL tickers have data
    sorted_dates = sorted(all_dates)
    available_tickers = list(histories.keys())

    # Filter to dates with all tickers present
    valid_dates = [d for d in sorted_dates if all(t in date_prices.get(d, {}) for t in available_tickers)]

    if len(valid_dates) < 10:
        return {}

    # Compute daily returns
    returns: dict[str, list[float]] = {t: [] for t in available_tickers}
    for i in range(1, len(valid_dates)):
        prev_d = valid_dates[i - 1]
        curr_d = valid_dates[i]
        for t in available_tickers:
            prev_price = date_prices[prev_d][t]
            curr_price = date_prices[curr_d][t]
            ret = (curr_price - prev_price) / prev_price
            returns[t].append(ret)

    return returns


def compute_correlations(returns: dict[str, list[float]], top_n: int = 10) -> list[dict]:
    """Compute pairwise correlations from return series.

    Returns list of {ticker_a, ticker_b, correlation, n_observations}
    sorted by abs(correlation) descending.
    """
    import math

    tickers = list(returns.keys())
    if len(tickers) < 2:
        return []

    pairs = []
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            ta, tb = tickers[i], tickers[j]
            ra, rb = returns[ta], returns[tb]
            n = min(len(ra), len(rb))
            if n < 10:
                continue

            mean_a = sum(ra[:n]) / n
            mean_b = sum(rb[:n]) / n

            cov = sum((ra[k] - mean_a) * (rb[k] - mean_b) for k in range(n)) / (n - 1)
            var_a = sum((ra[k] - mean_a) ** 2 for k in range(n)) / (n - 1)
            var_b = sum((rb[k] - mean_b) ** 2 for k in range(n)) / (n - 1)

            if var_a <= 0 or var_b <= 0:
                continue

            corr = cov / math.sqrt(var_a * var_b)
            pairs.append({
                "ticker_a": ta,
                "ticker_b": tb,
                "correlation": round(corr, 4),
                "n_observations": n,
                "high_correlation": abs(corr) > 0.8,
            })

    pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)
    return pairs[:top_n]


def compute_realized_beta(
    returns: dict[str, list[float]],
    benchmark: str = "SPY",
) -> dict[str, Optional[float]]:
    """Compute realized beta vs benchmark for each ticker.

    beta_i = cov(r_i, r_benchmark) / var(r_benchmark)
    """
    if benchmark not in returns:
        return {}

    rb = returns[benchmark]
    n_bench = len(rb)
    if n_bench < 10:
        return {}

    mean_b = sum(rb) / n_bench
    var_b = sum((rb[k] - mean_b) ** 2 for k in range(n_bench)) / (n_bench - 1)
    if var_b <= 0:
        return {}

    betas: dict[str, Optional[float]] = {}
    for ticker, ra in returns.items():
        if ticker == benchmark:
            betas[ticker] = 1.0
            continue
        n = min(len(ra), n_bench)
        if n < 10:
            betas[ticker] = None
            continue
        mean_a = sum(ra[:n]) / n
        mean_b_n = sum(rb[:n]) / n
        var_b_n = sum((rb[k] - mean_b_n) ** 2 for k in range(n)) / (n - 1)
        if var_b_n <= 0:
            betas[ticker] = None
            continue
        cov = sum((ra[k] - mean_a) * (rb[k] - mean_b_n) for k in range(n)) / (n - 1)
        betas[ticker] = round(cov / var_b_n, 4)

    return betas


def compute_portfolio_beta(
    betas: dict[str, Optional[float]],
    weights: dict[str, float],
) -> Optional[float]:
    """Compute portfolio beta as weighted average of position betas.

    weights = {ticker: dollar_exposure}
    """
    total_weight = sum(abs(w) for t, w in weights.items() if betas.get(t) is not None)
    if total_weight <= 0:
        return None

    portfolio_beta = sum(
        betas[t] * abs(w) / total_weight
        for t, w in weights.items()
        if betas.get(t) is not None
    )
    return round(portfolio_beta, 4)


def compute_var_95(port_delta: float, daily_returns: list[float]) -> float | None:
    """Compute 1-day 95% VaR using parametric method.

    Uses: VaR = abs(port_delta) * daily_vol * 1.645
    where daily_vol = std(daily_returns)
    """
    if not daily_returns or port_delta == 0:
        return None
    import numpy as np
    daily_vol = float(np.std(daily_returns))
    if daily_vol <= 0:
        return None
    var_95 = abs(port_delta) * daily_vol * 1.645
    return round(var_95, 2)


def compute_stress_tests(
    portfolio_delta: float,
    portfolio_gamma: float = 0.0,
    underlying_price: float = 100.0,
) -> list[dict]:
    """Compute approximate portfolio P&L for market moves.

    Uses delta-gamma approximation:
    P&L ~ delta * dS + 0.5 * gamma * dS^2
    where dS = move_pct * underlying_price
    """
    moves = [-0.05, -0.02, -0.01, 0.01, 0.02, 0.05]
    results = []
    for move in moves:
        dS = move * underlying_price
        pnl_est = portfolio_delta * move + 0.5 * portfolio_gamma * dS * move
        results.append({
            "move_pct": round(move * 100, 1),
            "pnl_estimate": round(pnl_est, 2),
        })
    return results
