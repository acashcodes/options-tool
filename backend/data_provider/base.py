from __future__ import annotations

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
            high_52w, low_52w, earnings_date, market_cap, volume
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
            implied_volatility, in_the_money
        """
        ...

    @abstractmethod
    def get_history(self, symbol: str, period: str = "1y") -> list[dict[str, Any]]:
        """Get historical price data.

        Returns list of dicts with keys: date, open, high, low, close, volume
        """
        ...
