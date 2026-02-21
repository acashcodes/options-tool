from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any


class DataProvider(ABC):
    """Abstract base class for market data providers.

    Implement this interface to swap between data sources
    (e.g., yfinance now, Schwab API later) without changing
    the rest of the application.
    """

    @abstractmethod
    def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get current quote data for a ticker.

        Returns dict with keys:
            symbol, name, price, previous_close, change, change_percent,
            high_52w, low_52w, earnings_date, market_cap, volume,
            current_iv, hv_20d, iv_hv_ratio, iv_rank, iv_percentile
        """
        ...

    @abstractmethod
    def get_options_expirations(self, symbol: str) -> list[str]:
        """Get available options expiration dates for a ticker.

        Returns list of date strings in YYYY-MM-DD format.
        """
        ...

    @abstractmethod
    def get_options_chain(self, symbol: str, expiration: str) -> dict[str, Any]:
        """Get options chain for a ticker and expiration date.

        Returns dict with keys:
            calls: list of option dicts
            puts: list of option dicts

        Each option dict has keys:
            strike, last_price, bid, ask, volume, open_interest,
            implied_volatility, in_the_money, delta, gamma, theta, vega
        """
        ...

    @abstractmethod
    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> list[dict[str, Any]]:
        """Get historical price data.

        Returns list of dicts with keys: date, open, high, low, close, volume
        """
        ...

    # ------------------------------------------------------------------
    # Concrete helpers (built on top of the abstract methods)
    # ------------------------------------------------------------------

    def get_quote_light(self, symbol: str) -> dict[str, Any]:
        """Lightweight quote: price + change only. No IV/HV computation.

        Default delegates to full get_quote(). Override for speed.
        """
        q = self.get_quote(symbol)
        return {
            "symbol": q.get("symbol"),
            "name": q.get("name"),
            "price": q.get("price"),
            "previous_close": q.get("previous_close"),
            "change": q.get("change"),
            "change_percent": q.get("change_percent"),
        }

    def get_iv_metrics(self, symbol: str, current_price: float | None = None) -> dict[str, Any]:
        """Compute implied-volatility and historical-volatility metrics.

        Returns dict with keys:
            current_iv   – ATM implied volatility (%) from the nearest expiration,
                           or None if unavailable.
            hv_20d       – 20-day realised (historical) volatility annualised (%),
                           or None if unavailable.
            iv_hv_ratio  – current_iv / hv_20d, or None if either is None.
            iv_rank      – Current IV's position in 52-week IV range (0-100%).
            iv_percentile – % of days in last year with IV below current (0-100%).
        """
        current_iv = self._compute_atm_iv(symbol, current_price)
        hv_20d = self._compute_hv(symbol, window=20)

        iv_hv_ratio: float | None = None
        if current_iv is not None and hv_20d is not None and hv_20d != 0:
            iv_hv_ratio = round(current_iv / hv_20d, 2)

        # IV Rank & Percentile from rolling HV as a proxy for historical IV
        iv_rank, iv_percentile = self._compute_iv_rank_percentile(symbol, current_iv)

        return {
            "current_iv": current_iv,
            "hv_20d": hv_20d,
            "iv_hv_ratio": iv_hv_ratio,
            "iv_rank": iv_rank,
            "iv_percentile": iv_percentile,
        }

    # --- private helpers ------------------------------------------------

    def _compute_atm_iv(self, symbol: str, current_price: float | None = None) -> float | None:
        """Return ATM IV (%) for the nearest expiration, or None."""
        try:
            expirations = self.get_options_expirations(symbol)
            if not expirations:
                return None

            nearest_exp = expirations[0]
            chain = self.get_options_chain(symbol, nearest_exp)

            # Determine current price
            price = current_price or chain.get("underlying_price")
            if price is None:
                return None

            call_iv = self._nearest_strike_iv(chain.get("calls", []), price)
            put_iv = self._nearest_strike_iv(chain.get("puts", []), price)

            ivs = [v for v in (call_iv, put_iv) if v is not None]
            if not ivs:
                return None

            return round(sum(ivs) / len(ivs), 2)
        except Exception:
            return None

    @staticmethod
    def _nearest_strike_iv(options: list[dict[str, Any]], price: float) -> float | None:
        """Find the option whose strike is closest to *price* and return its IV."""
        best: dict[str, Any] | None = None
        best_diff = float("inf")
        for opt in options:
            strike = opt.get("strike")
            iv = opt.get("implied_volatility")
            if strike is None or iv is None:
                continue
            diff = abs(strike - price)
            if diff < best_diff:
                best_diff = diff
                best = opt
        return best["implied_volatility"] if best is not None else None

    def _compute_iv_rank_percentile(
        self, symbol: str, current_iv: float | None
    ) -> tuple[float | None, float | None]:
        """Compute IV Rank and IV Percentile using rolling 20-day HV as a proxy.

        IV Rank = (current - 52w low) / (52w high - 52w low) × 100
        IV Percentile = % of observations below current × 100
        """
        if current_iv is None:
            return None, None

        try:
            history = self.get_history(symbol, period="1y")
            if len(history) < 30:
                return None, None

            closes = [day["close"] for day in history]

            # Compute rolling 20-day HV series
            window = 20
            hv_series: list[float] = []
            for i in range(window, len(closes)):
                segment = closes[i - window : i + 1]
                log_rets = [
                    math.log(segment[j] / segment[j - 1])
                    for j in range(1, len(segment))
                    if segment[j] > 0 and segment[j - 1] > 0
                ]
                if len(log_rets) < window:
                    continue
                mean = sum(log_rets) / len(log_rets)
                var = sum((r - mean) ** 2 for r in log_rets) / (len(log_rets) - 1)
                hv = math.sqrt(var) * math.sqrt(252) * 100
                hv_series.append(hv)

            if not hv_series:
                return None, None

            low_52w = min(hv_series)
            high_52w = max(hv_series)

            # IV Rank
            iv_rank: float | None = None
            if high_52w > low_52w:
                iv_rank = round(((current_iv - low_52w) / (high_52w - low_52w)) * 100, 1)
                iv_rank = max(0, min(100, iv_rank))

            # IV Percentile
            below = sum(1 for h in hv_series if h < current_iv)
            iv_percentile = round((below / len(hv_series)) * 100, 1)

            return iv_rank, iv_percentile
        except Exception:
            return None, None

    def _compute_hv(self, symbol: str, window: int = 20) -> float | None:
        """Return annualised historical volatility (%) over *window* trading days."""
        try:
            # Fetch ~30 calendar-day history to ensure we have enough trading days
            history = self.get_history(symbol, period="3mo")
            if len(history) < window + 1:
                return None

            # Use the most recent (window + 1) closes to get *window* returns
            closes = [day["close"] for day in history[-(window + 1):]]
            log_returns = [
                math.log(closes[i] / closes[i - 1])
                for i in range(1, len(closes))
                if closes[i - 1] > 0 and closes[i] > 0
            ]
            if len(log_returns) < window:
                return None

            mean = sum(log_returns) / len(log_returns)
            variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
            std_dev = math.sqrt(variance)
            annualised = std_dev * math.sqrt(252) * 100  # percentage
            return round(annualised, 2)
        except Exception:
            return None
