from __future__ import annotations

import math
from datetime import datetime, date
from typing import Any, Optional

import yfinance as yf

from .base import DataProvider
from greeks import compute_greeks
from cache import TTLCache
import time_utils
import iv_solver


class YFinanceProvider(DataProvider):
    """Market data provider backed by yfinance, with TTL caching."""

    def __init__(self):
        self._quote_cache = TTLCache(5)
        self._quote_light_cache = TTLCache(5)
        self._chain_cache = TTLCache(15)
        self._history_cache = TTLCache(60)
        self._expirations_cache = TTLCache(60)

    def get_quote(self, symbol: str) -> dict[str, Any]:
        cached = self._quote_cache.get(symbol.upper())
        if cached is not None:
            return cached

        ticker = yf.Ticker(symbol)
        info = ticker.info

        price = _get_fast_info_attr(ticker, "last_price")
        if price is None:
            price = info.get("currentPrice") or info.get("regularMarketPrice")

        previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        if previous_close is None:
            previous_close = _get_fast_info_attr(ticker, "previous_close")

        change = None
        change_percent = None
        if price is not None and previous_close is not None:
            change = price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close else None

        # Earnings date
        earnings_date = None
        earnings_dates = info.get("earningsTimestamps") or []
        if not earnings_dates:
            try:
                cal = ticker.calendar
                if cal is not None:
                    if isinstance(cal, dict) and "Earnings Date" in cal:
                        ed = cal["Earnings Date"]
                        if isinstance(ed, list) and len(ed) > 0:
                            earnings_date = str(ed[0].date()) if hasattr(ed[0], "date") else str(ed[0])
                        elif hasattr(ed, "date"):
                            earnings_date = str(ed.date())
                    elif hasattr(cal, "columns") and "Earnings Date" in cal.columns:
                        vals = cal["Earnings Date"].tolist()
                        if vals:
                            earnings_date = str(vals[0].date()) if hasattr(vals[0], "date") else str(vals[0])
            except Exception:
                pass

        # Dividend yield (decimal, e.g. 0.015 for 1.5%)
        dividend_yield = _safe_float_raw(info.get("dividendYield"))

        # IV / HV metrics
        iv_metrics = self.get_iv_metrics(
            symbol,
            current_price=price if price is not None else None,
        )

        result = {
            "symbol": symbol.upper(),
            "name": info.get("shortName") or info.get("longName") or symbol.upper(),
            "price": price,
            "previous_close": previous_close,
            "change": change,
            "change_percent": change_percent,
            "high_52w": info.get("fiftyTwoWeekHigh"),
            "low_52w": info.get("fiftyTwoWeekLow"),
            "earnings_date": earnings_date,
            "market_cap": info.get("marketCap"),
            "volume": info.get("volume") or info.get("regularMarketVolume"),
            "current_iv": iv_metrics.get("current_iv"),
            "hv_20d": iv_metrics.get("hv_20d"),
            "iv_hv_ratio": iv_metrics.get("iv_hv_ratio"),
            "iv_rank": iv_metrics.get("iv_rank"),
            "iv_percentile": iv_metrics.get("iv_percentile"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "beta": _safe_float_raw(info.get("beta")),
            "dividend_yield": dividend_yield,
        }
        self._quote_cache.set(symbol.upper(), result)
        return result

    def get_quote_light(self, symbol: str) -> dict[str, Any]:
        """Fast quote: price + change, no IV/HV computation."""
        cached = self._quote_light_cache.get(symbol.upper())
        if cached is not None:
            return cached

        ticker = yf.Ticker(symbol)
        info = ticker.info

        price = _get_fast_info_attr(ticker, "last_price")
        if price is None:
            price = info.get("currentPrice") or info.get("regularMarketPrice")

        previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        if previous_close is None:
            previous_close = _get_fast_info_attr(ticker, "previous_close")

        change = None
        change_percent = None
        if price is not None and previous_close is not None:
            change = price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close else None

        result = {
            "symbol": symbol.upper(),
            "name": info.get("shortName") or info.get("longName") or symbol.upper(),
            "price": price,
            "previous_close": previous_close,
            "change": change,
            "change_percent": change_percent,
        }
        self._quote_light_cache.set(symbol.upper(), result)
        return result

    def get_options_expirations(self, symbol: str) -> list[str]:
        cached = self._expirations_cache.get(symbol.upper())
        if cached is not None:
            return cached
        ticker = yf.Ticker(symbol)
        result = list(ticker.options)
        self._expirations_cache.set(symbol.upper(), result)
        return result

    def get_options_chain(self, symbol: str, expiration: str) -> dict[str, Any]:
        cache_key = f"{symbol.upper()}:{expiration}"
        cached = self._chain_cache.get(cache_key)
        if cached is not None:
            return cached

        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(expiration)

        # Get current price
        price = None
        try:
            price = _get_fast_info_attr(ticker, "last_price")
            if price is None:
                price = ticker.info.get("currentPrice") or ticker.info.get("regularMarketPrice")
        except Exception:
            pass

        # Compute time to expiration using timezone-aware utility
        t_years = time_utils.year_frac_to(expiration)

        # Get risk-free rate and dividend yield
        from assumptions import default_risk_free_rate
        risk_free_rate = default_risk_free_rate(self)
        q = 0.0
        try:
            info = ticker.info
            div_yield = info.get("dividendYield")
            if div_yield is not None:
                q = float(div_yield)
        except Exception:
            pass

        def process_options(df, option_type: str) -> list[dict]:
            rows = []
            for _, row in df.iterrows():
                strike = float(row["strike"])
                if option_type == "call":
                    itm = price is not None and strike < price
                else:
                    itm = price is not None and strike > price

                iv = row.get("impliedVolatility")
                iv_source = "chain"
                if iv is not None and not (isinstance(iv, float) and math.isnan(iv)):
                    iv_decimal = float(iv)
                    iv_pct = iv_decimal * 100
                else:
                    iv_decimal = None
                    iv_pct = None
                    iv_source = "missing"

                # IV solver fallback
                if iv_decimal is None and price is not None and price > 0 and t_years > 0:
                    bid = _safe_float_raw(row.get("bid"))
                    ask = _safe_float_raw(row.get("ask"))
                    last = _safe_float_raw(row.get("lastPrice"))
                    mid = None
                    if bid is not None and ask is not None and bid > 0 and ask > 0:
                        mid = (bid + ask) / 2
                    market_price = mid or last
                    if market_price and market_price > 0:
                        solved = iv_solver.implied_vol_from_price(
                            market_price=market_price,
                            S=price, K=strike, t=t_years,
                            r=risk_free_rate, q=q,
                            option_type=option_type,
                        )
                        if solved is not None:
                            iv_decimal = solved
                            iv_pct = solved * 100
                            iv_source = "solved"

                # Compute Greeks
                greeks = {}
                if price is not None and iv_decimal is not None and iv_decimal > 0 and t_years > 0:
                    greeks = compute_greeks(
                        S=price, K=strike, t=t_years,
                        r=risk_free_rate, sigma=iv_decimal,
                        option_type=option_type, q=q,
                    )

                rows.append({
                    "contract_symbol": row.get("contractSymbol", ""),
                    "strike": strike,
                    "last_price": _safe_float_raw(row.get("lastPrice")),
                    "bid": _safe_float_raw(row.get("bid")),
                    "ask": _safe_float_raw(row.get("ask")),
                    "volume": _safe_int(row.get("volume")),
                    "open_interest": _safe_int(row.get("openInterest")),
                    "implied_volatility": iv_pct,
                    "iv_source": iv_source,
                    "in_the_money": itm,
                    "delta": greeks.get("delta"),
                    "gamma": greeks.get("gamma"),
                    "theta": greeks.get("theta"),
                    "vega": greeks.get("vega"),
                })
            return rows

        result = {
            "calls": process_options(chain.calls, "call"),
            "puts": process_options(chain.puts, "put"),
            "underlying_price": price,
            "dividend_yield": q,
        }
        self._chain_cache.set(cache_key, result)
        return result

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> list[dict[str, Any]]:
        cache_key = f"{symbol.upper()}:{period}:{interval}"
        cached = self._history_cache.get(cache_key)
        if cached is not None:
            return cached

        ticker = yf.Ticker(symbol)

        if period == "3y":
            from datetime import timedelta
            start = date.today() - timedelta(days=3 * 365)
            hist = ticker.history(start=str(start), interval=interval)
        else:
            hist = ticker.history(period=period, interval=interval)

        intraday = interval in ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h")
        rows = []
        for dt, row in hist.iterrows():
            if intraday:
                date_str = str(dt)
            else:
                date_str = str(dt.date()) if hasattr(dt, "date") else str(dt)
            rows.append({
                "date": date_str,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            })

        self._history_cache.set(cache_key, rows)
        return rows


def _get_fast_info_attr(ticker, attr_name):
    """Safely get an attribute from fast_info."""
    fi = getattr(ticker, "fast_info", None)
    if fi is None:
        return None
    val = getattr(fi, attr_name, None)
    if val is not None:
        return val
    if hasattr(fi, "get"):
        return fi.get(attr_name)
    return None


def _safe_float_raw(val) -> float | None:
    """Convert to float without rounding. Returns None for NaN/invalid."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
