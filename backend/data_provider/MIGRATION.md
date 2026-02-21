# Data Provider Migration Guide

## Architecture

The app uses a **DataProvider abstraction layer** so market data sources can be swapped without changing any frontend or route code. The only file that references a concrete provider is `main.py`.

```
data_provider/
  base.py              # Abstract base class (DataProvider)
  yfinance_provider.py # Current implementation (yfinance)
  __init__.py          # Exports DataProvider + YFinanceProvider
```

## How to Add a New Provider (e.g., Schwab API)

### 1. Create the provider file

Create `data_provider/schwab_provider.py`:

```python
from data_provider.base import DataProvider

class SchwabProvider(DataProvider):
    def __init__(self, api_key: str, api_secret: str, redirect_uri: str):
        # Initialize Schwab API client
        # See: https://developer.schwab.com/
        pass

    def get_quote(self, symbol: str) -> dict:
        # Must return dict with keys:
        #   symbol, name, price, previous_close, change, change_percent,
        #   high_52w, low_52w, earnings_date, market_cap, volume,
        #   current_iv, hv_20d, iv_hv_ratio, iv_rank, iv_percentile
        pass

    def get_options_expirations(self, symbol: str) -> list[str]:
        # Must return list of "YYYY-MM-DD" strings
        pass

    def get_options_chain(self, symbol: str, expiration: str) -> dict:
        # Must return {"calls": [...], "puts": [...]}
        # Each option dict needs:
        #   strike, last_price, bid, ask, volume, open_interest,
        #   implied_volatility, in_the_money, delta, gamma, theta, vega
        pass

    def get_history(self, symbol: str, period: str = "1y") -> list[dict]:
        # Must return list of dicts with:
        #   date, open, high, low, close, volume
        pass
```

### 2. Register it

In `data_provider/__init__.py`, add:

```python
from .schwab_provider import SchwabProvider
```

### 3. Swap in `main.py`

Change the single line in `main.py`:

```python
# Before:
provider = YFinanceProvider()

# After:
provider = SchwabProvider(
    api_key=os.environ["SCHWAB_API_KEY"],
    api_secret=os.environ["SCHWAB_API_SECRET"],
    redirect_uri="https://localhost:8000/callback",
)
```

That's it. No other files need to change.

## Concrete Methods to Implement

| Method | Returns | Notes |
|--------|---------|-------|
| `get_quote(symbol)` | dict | Price, change, IV metrics, earnings date |
| `get_options_expirations(symbol)` | list[str] | Available expiry dates |
| `get_options_chain(symbol, expiration)` | dict | Calls + puts with greeks |
| `get_history(symbol, period)` | list[dict] | OHLCV bars |

### Optional Override

| Method | Default Behavior |
|--------|-----------------|
| `get_quote_light(symbol)` | Delegates to `get_quote()`. Override if you can fetch price-only data faster. |

### Built-in Methods (no override needed)

These are computed from the abstract methods automatically:

- `get_iv_metrics()` — computes IV rank, IV percentile, HV from history + chain data
- `_compute_atm_iv()` — finds ATM IV from nearest chain
- `_compute_hv()` — annualized historical volatility from price history
- `_compute_iv_rank_percentile()` — IV rank/percentile from rolling HV series

If the Schwab API provides these directly (it does for greeks), you can return them from `get_quote()` and the base class helpers won't be called.

## Schwab API Specifics

- **Auth:** OAuth 2.0 with PKCE flow. You'll need to handle token refresh.
- **Rate limits:** 120 requests/minute for market data.
- **Package:** Use `schwab-py` (unofficial Python client) or call REST endpoints directly.
- **Key advantage:** Real-time quotes, native greeks in chain data, account integration for live positions.

## Environment Variables

For the Schwab provider, set these before starting the backend:

```bash
export SCHWAB_API_KEY="your-app-key"
export SCHWAB_API_SECRET="your-app-secret"
```
