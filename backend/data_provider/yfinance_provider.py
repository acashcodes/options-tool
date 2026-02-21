from __future__ import annotations

import math
from datetime import datetime, date
from typing import Any, Optional

import yfinance as yf

from .base import DataProvider
from greeks import compute_greeks


class YFinanceProvider(DataProvider):
    """Market data provider backed by yfinance."""

    def get_quote(self, symbol: str) -> dict[str, Any]:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Get current price — try fast_info first, fall back to info dict
        price = _get_fast_info_attr(ticker, "last_price")
        if price is None:
            price = info.get("currentPrice") or info.get("regularMarketPrice")

        previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        if previous_close is None:
            previous_close = _get_fast_info_attr(ticker, "previous_close")

        change = None
        change_percent = None
        if price is not None and previous_close is not None:
            change = round(price - previous_close, 2)
            change_percent = round((change / previous_close) * 100, 2)

        # Earnings date
        earnings_date = None
        earnings_dates = info.get("earningsTimestamps") or []
        if not earnings_dates:
            # Try the calendar approach
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

        # --- IV / HV metrics (best-effort, nulls on failure) -----------
        iv_metrics = self.get_iv_metrics(
            symbol,
            current_price=price if price is not None else None,
        )

        return {
            "symbol": symbol.upper(),
            "name": info.get("shortName") or info.get("longName") or symbol.upper(),
            "price": round(price, 2) if price is not None else None,
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
            "beta": _safe_float(info.get("beta")),
        }

    def get_quote_light(self, symbol: str) -> dict[str, Any]:
        """Fast quote: price + change, no IV/HV computation."""
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
            change = round(price - previous_close, 2)
            change_percent = round((change / previous_close) * 100, 2) if previous_close else None

        return {
            "symbol": symbol.upper(),
            "name": info.get("shortName") or info.get("longName") or symbol.upper(),
            "price": round(price, 2) if price is not None else None,
            "previous_close": previous_close,
            "change": change,
            "change_percent": change_percent,
        }

    def get_options_expirations(self, symbol: str) -> list[str]:
        ticker = yf.Ticker(symbol)
        return list(ticker.options)

    def get_options_chain(self, symbol: str, expiration: str) -> dict[str, Any]:
        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(expiration)

        # Get current price for ITM determination
        price = None
        try:
            price = _get_fast_info_attr(ticker, "last_price")
            if price is None:
                price = ticker.info.get("currentPrice") or ticker.info.get("regularMarketPrice")
        except Exception:
            pass

        # Compute time to expiration in years
        t_years = _time_to_expiry_years(expiration)
        risk_free_rate = 0.045  # ~4.5% approximate current rate

        def process_options(df, option_type: str) -> list[dict]:
            rows = []
            for _, row in df.iterrows():
                strike = float(row["strike"])
                if option_type == "call":
                    itm = price is not None and strike < price
                else:
                    itm = price is not None and strike > price

                iv = row.get("impliedVolatility")
                if iv is not None and not (isinstance(iv, float) and math.isnan(iv)):
                    iv_decimal = float(iv)  # yfinance gives decimal (e.g. 0.30)
                    iv_pct = round(iv_decimal * 100, 2)  # Convert to percentage for display
                else:
                    iv_decimal = None
                    iv_pct = None

                # Compute Greeks if we have what we need
                greeks = {}
                if price is not None and iv_decimal is not None and iv_decimal > 0 and t_years > 0:
                    greeks = compute_greeks(
                        S=price,
                        K=strike,
                        t=t_years,
                        r=risk_free_rate,
                        sigma=iv_decimal,
                        option_type=option_type,
                    )

                rows.append({
                    "contract_symbol": row.get("contractSymbol", ""),
                    "strike": strike,
                    "last_price": _safe_float(row.get("lastPrice")),
                    "bid": _safe_float(row.get("bid")),
                    "ask": _safe_float(row.get("ask")),
                    "volume": _safe_int(row.get("volume")),
                    "open_interest": _safe_int(row.get("openInterest")),
                    "implied_volatility": iv_pct,
                    "in_the_money": itm,
                    "delta": greeks.get("delta"),
                    "gamma": greeks.get("gamma"),
                    "theta": greeks.get("theta"),
                    "vega": greeks.get("vega"),
                })
            return rows

        return {
            "calls": process_options(chain.calls, "call"),
            "puts": process_options(chain.puts, "put"),
            "underlying_price": round(price, 2) if price is not None else None,
        }

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> list[dict[str, Any]]:
        ticker = yf.Ticker(symbol)

        # 3y is not a native yfinance period — use start date instead
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
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return rows


def _get_fast_info_attr(ticker, attr_name):
    """Safely get an attribute from fast_info (handles both dict-like and property access)."""
    fi = getattr(ticker, "fast_info", None)
    if fi is None:
        return None
    # Try property access first (yfinance >= 1.x)
    val = getattr(fi, attr_name, None)
    if val is not None:
        return val
    # Fall back to dict-like access (older yfinance)
    if hasattr(fi, "get"):
        return fi.get(attr_name)
    return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else round(f, 2)
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        i = int(val)
        return i
    except (ValueError, TypeError):
        return None


def _time_to_expiry_years(expiration: str) -> float:
    """Convert an expiration date string (YYYY-MM-DD) to time in years from today."""
    try:
        exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        today = date.today()
        days = (exp_date - today).days
        return max(days, 0) / 365.0
    except Exception:
        return 0.0
