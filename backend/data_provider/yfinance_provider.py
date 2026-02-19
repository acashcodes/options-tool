from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional

import yfinance as yf

from .base import DataProvider


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
                    iv = round(float(iv) * 100, 2)  # Convert to percentage
                else:
                    iv = None

                rows.append({
                    "contract_symbol": row.get("contractSymbol", ""),
                    "strike": strike,
                    "last_price": _safe_float(row.get("lastPrice")),
                    "bid": _safe_float(row.get("bid")),
                    "ask": _safe_float(row.get("ask")),
                    "volume": _safe_int(row.get("volume")),
                    "open_interest": _safe_int(row.get("openInterest")),
                    "implied_volatility": iv,
                    "in_the_money": itm,
                })
            return rows

        return {
            "calls": process_options(chain.calls, "call"),
            "puts": process_options(chain.puts, "put"),
            "underlying_price": round(price, 2) if price is not None else None,
        }

    def get_history(self, symbol: str, period: str = "1y") -> list[dict[str, Any]]:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        rows = []
        for date, row in hist.iterrows():
            rows.append({
                "date": str(date.date()) if hasattr(date, "date") else str(date),
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
