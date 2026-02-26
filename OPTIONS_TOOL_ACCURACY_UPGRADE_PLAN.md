# Options Tool — Accuracy Upgrade Implementation Plan (All Changes)

**Date:** 2026-02-22  
**Goal:** Make every computed number internally *math-consistent*, *unit-consistent*, and *reproducible*, with a single source of truth for pricing/payoff logic and strong automated tests.

This document is written as an implementation checklist for Claude (or any engineer) to execute without ambiguity.

---

## Non‑negotiable accuracy rules (apply to all work)

### A. One canonical math engine
- There must be **exactly one** canonical implementation of:
  - option pricing (BSM / chosen model)
  - Greeks
  - payoff-at-expiration
  - strategy metrics (max profit/loss, breakevens, capital required, risk/reward)
  - probability-of-profit (PoP) under stated assumptions
- **Frontend must not duplicate formulas** (no JS Black‑Scholes, no JS payoff math for anything used in metrics).

### B. Never round until the final presentation layer
- Do **not** `round()` inside core math functions.
- Do **not** `toFixed()` inside computations.
- Rounding rules:
  - **API** returns full-precision floats (or decimals as strings).
  - **Frontend** formats for display only.
  - If you must round for deterministic snapshots, do it **once** in a `format_*` layer.

### C. Define and enforce units everywhere
- **Prices / premiums**: USD **per share** (options quotes are per share).  
- **Contract multiplier**: default `100` unless explicitly specified; always multiply when converting to per-contract dollars.
- **Rates**: decimals (5% = `0.05`) in backend.
- **IV**: decimals in backend (`0.30` = 30%); frontend may display percent.
- **Time**: years as a fraction of real time to expiry using a defined day-count convention.

### D. Define and enforce sign conventions everywhere
- Convert user legs into signed quantities in one place:
  - options: `signed_contracts = +qty` for BUY, `-qty` for SELL
  - stock: `signed_shares = +qty` for BUY, `-qty` for SELL
- Entry cashflow:
  - BUY = cash outflow (negative), SELL = inflow (positive)
- P&L:
  - `pnl = current_value - entry_cost` (where entry_cost can be negative for credits; be explicit).

### E. Every numeric output must have an automated test
- For each metric shown in UI (net premium, capital required, max profit/loss, breakevens, PoP, greeks, day P&L):
  - Add unit tests with known values.
  - Add regression tests (“golden” fixtures).
- Any bugfix must add a test that fails before and passes after.

---

## Quick list of required upgrades (all 6 + additional accuracy upgrades)

1) **Centralize strategy math in backend** (pricing/payoff/metrics/curves) and make frontend use it exclusively.  
2) **Market data performance + robustness**: caching + backend strike filtering; remove premature rounding; unify rate/time assumptions.  
3) **Portfolio correctness**: fix options day P&L, introduce mark-history, and move persistence to SQLite for consistency.  
4) **Add Stock legs** so stock+options strategies (covered call/collar/etc.) compute correctly.  
5) **Execution-realistic pricing**: bid/ask-aware entry/mark, slippage model, better liquidity filters.  
6) **Correlation + beta + stress tests** in portfolio analytics.  

Additional accuracy upgrades (strongly recommended):
7) **Correct time-to-expiry** using timezone-aware datetimes (fixes 0DTE / expiry-day errors).  
8) **Add dividend yield (q) to pricing/Greeks** (Black‑Scholes‑Merton), and expose assumptions in UI/API.  
9) **Fix ^TNX scaling** and use it consistently as risk-free input (display + calculations).  
10) **Implied-vol solver fallback** when IV missing/NaN (use market mid + brentq).  
11) **Replace ad-hoc numeric logic with deterministic algorithms** (exact breakevens/max loss for piecewise-linear expiration payoffs).  
12) **Create a single “Assumptions” object** persisted in UI (pricing mode, r, q, day-count), passed to every analysis call.

---

# WORK PACKAGES (do in order)

## WP0 — Test + Validation Harness (foundation)

### Files to add
- `backend/tests/test_greeks_pytest.py` (port `backend/test_greeks.py` into pytest)
- `backend/tests/test_strategy_math_pytest.py` (port `backend/test_strategy_math.py` into pytest)
- `backend/tests/test_time_utils.py`
- `backend/tests/test_strategy_analyze_endpoint.py`

### Changes
1. Add `pytest` to `backend/requirements.txt`.
2. Create a `backend/tests/` package and move/port existing test scripts:
   - Keep the existing scripts if you want, but pytest should be the authoritative runner.
3. Add a CI-ish local command to README (or Makefile):
   - `cd backend && pytest -q`

### Acceptance criteria
- `pytest` runs clean and validates:
  - Black‑Scholes prices/Greeks sanity
  - put-call parity
  - payoff formulas (long call/put, spreads, condor) exactly as defined
- This must run before any other WP so refactors don’t break silently.

---

## WP1 — Time, Rate, Dividend Yield, and Rounding Refactor (accuracy baseline)

### 1.1 Create a single time utility module (fixes 0DTE math bugs)

**Problem today:** time-to-expiry is computed as `(exp_date - today).days / 365`, which becomes **0 on expiration day**, causing Greeks/prices to collapse incorrectly.

#### Files to add
- `backend/time_utils.py`

#### Implement in `backend/time_utils.py`
- Use `zoneinfo.ZoneInfo("America/New_York")` (Python 3.9+).
- Constants:
  - `NY_TZ = ZoneInfo("America/New_York")`
  - `EXPIRY_HOUR = 16` (4:00pm ET)
  - `SECONDS_IN_YEAR = 365.0 * 24 * 60 * 60` (ACT/365)
- Functions (exact signatures):
  - `def now_et() -> datetime:`
  - `def expiry_dt_et(expiration_date: str) -> datetime:`  # expiration_date is YYYY-MM-DD; return 16:00 ET
  - `def year_frac_to(expiration_date: str, as_of: datetime | None = None) -> float:`
    - `as_of` default `now_et()`
    - return `max((expiry_dt_et(exp) - as_of).total_seconds(), 0) / SECONDS_IN_YEAR`
  - `def days_to(expiration_date: str, as_of: datetime | None = None) -> float:`
    - same but in days (seconds / 86400)

#### Update all callers
- `backend/data_provider/yfinance_provider.py`
  - replace `_time_to_expiry_years()` with `time_utils.year_frac_to(expiration)`
- `backend/portfolio_enrichment.py`
  - replace `_time_to_expiry()` with `time_utils.year_frac_to(expiration)`
- Any place that assumes midnight expiry must be replaced.

#### Tests
- `backend/tests/test_time_utils.py`
  - Freeze `as_of` to an ET morning time on expiration day and assert:
    - `year_frac_to(exp_today, as_of=10am ET)` is **> 0**
    - `year_frac_to(exp_today, as_of=5pm ET)` is 0

---

### 1.2 Fix ^TNX scaling and create a risk-free-rate source of truth

**Problem today:** UI displays “10Y Yield” as `^TNX.price%`, but `^TNX` is typically **10× the yield** (e.g., 44.50 represents 4.45%). This makes displayed yield and any derived r wrong by ~10× if used.

#### Files to add
- `backend/assumptions.py` (or `backend/settings.py`) — central assumptions

#### Implement in `backend/assumptions.py`
- Function:
  - `def tnx_to_yield_decimal(tnx_index_price: float | None) -> float | None:`
    - if None: return None
    - yield_percent = `tnx_index_price / 10.0`
    - yield_decimal = `yield_percent / 100.0`
    - equivalently `tnx_index_price / 1000.0`
- Function:
  - `def default_risk_free_rate(provider: DataProvider) -> float:`
    - try fetch `provider.get_quote_light("^TNX")`
    - compute decimal with `tnx_to_yield_decimal`
    - fallback to constant (e.g., `0.045`) ONLY if fetch fails
- Store this value in memory with TTL caching (see WP4 caching) so it doesn’t refetch constantly.

#### Update UI display
- `frontend/src/components/MarketOverviewBar.jsx`
  - For TNX display, render `data.tnx.price / 10` with `%` suffix (and similarly scale change/change_percent appropriately if change is in index points, not yield points).
  - Easiest: backend should return already-scaled `tnx_yield_percent` and `tnx_yield_change_percent` fields.

#### Recommended backend change (preferred for correctness)
- In `backend/routes/dashboard.py::market_overview()`
  - When fetching `^TNX`, transform:
    - `yield_pct = raw_price / 10`
    - `yield_change = raw_change / 10`
    - `yield_change_percent` should be `yield_change / (yield_pct - yield_change)` * 100 (or compute from raw change_percent carefully).
  - Return those values so frontend doesn’t guess.

#### Tests
- Add unit test for `tnx_to_yield_decimal(44.5) == 0.0445`.

---

### 1.3 Add dividend yield (q) to pricing + Greeks (Black‑Scholes‑Merton)

**Problem today:** pricing/Greeks ignore dividends. That can materially affect calls/puts and delta/theta.

#### Files to modify
- `backend/greeks.py`
- `backend/data_provider/yfinance_provider.py`
- `backend/routes/market.py` (if exposing greeks endpoint)
- `frontend` display (assumptions panel, optional)

#### Backend: update formulas in `backend/greeks.py`
- Add `q: float = 0.0` parameter to:
  - `_d1`, `_d2`, `bs_price`, `delta`, `gamma`, `theta`, `vega`, `rho`,
  - `compute_greeks`, `prob_above`, `prob_below`, `prob_itm`
- Use Black‑Scholes‑Merton formulas:
  - `d1 = (ln(S/K) + (r - q + 0.5*sigma^2)*t) / (sigma*sqrt(t))`
  - `d2 = d1 - sigma*sqrt(t)`
  - `call = S*exp(-q*t)*N(d1) - K*exp(-r*t)*N(d2)`
  - `put  = K*exp(-r*t)*N(-d2) - S*exp(-q*t)*N(-d1)`
  - `delta_call = exp(-q*t)*N(d1)`
  - `delta_put  = exp(-q*t)*(N(d1)-1)`
  - `gamma = exp(-q*t)*N'(d1)/(S*sigma*sqrt(t))`
  - `vega = S*exp(-q*t)*N'(d1)*sqrt(t)/100`  (per 1% IV)
  - Theta formulas must include `+ q*S*exp(-q*t)*N(±d1)` terms.
- Keep return units consistent with existing docstrings (theta $/day per share, vega per 1% IV per share, rho per 1% r per share).
- **Remove rounding inside `compute_greeks()`** (return raw floats). Rounding belongs in UI formatting.

#### Provider: fetch dividend yield
- In `backend/data_provider/yfinance_provider.py::get_quote()`:
  - Add `dividend_yield = info.get("dividendYield")`
    - yfinance typically returns decimal (e.g., 0.015)
  - Return it as decimal in API:
    - `"dividend_yield": _safe_float(dividend_yield)`  # no rounding
- In `get_options_chain()`:
  - Pass `q` into `compute_greeks` calls:
    - `q = quote_dividend_yield or 0.0`
  - Also include `"dividend_yield": q` at the chain-level response if helpful.

#### Update greeks endpoint
- `backend/routes/market.py`
  - Extend `GreeksRequest` and `BatchGreeksLeg` to include `q: float = 0.0`
  - Pass q through.

#### Tests
- Add a put-call parity test that includes q:
  - Parity with dividends: `C - P = S*exp(-q*t) - K*exp(-r*t)`
- Add benchmark case for a dividend-paying stock vs external calculator values (store expected values in test fixture).

---

### 1.4 Eliminate premature rounding across backend computations

#### Changes
- Search and remove/avoid `round()` inside:
  - `backend/greeks.py` (compute_greeks currently rounds)
  - `backend/data_provider/yfinance_provider.py` (price is rounded in quote/chain)
  - `backend/portfolio_enrichment.py` (rounding inside intermediate calculations)
  - `backend/routes/recommender.py::_mid()` rounds; keep full precision internally, round only in output formatting

#### Policy
- Keep internal as float.
- Only round:
  - when serializing for UI (e.g., in the route handler, or frontend formatting).
- Add a helper in backend:
  - `backend/formatting.py` with `money(x) -> float` to round to cents ONLY at output.

---



### 1.5 Implied Volatility Solver Fallback (brentq) — required for numeric completeness

**Problem today:** some chain rows can have missing/NaN IV. Any strategy math that depends on IV (BSM pricing, PoP, Greeks) becomes unstable or silently wrong if IV is missing.

**Rule:** If IV is missing and we have a usable market price (mid/bid/ask/last), we must be able to solve IV from price.

#### Files to add
- `backend/iv_solver.py`

#### Implement in `backend/iv_solver.py`
Use SciPy’s bracketing root finder (deterministic, robust):

```python
from __future__ import annotations

from typing import Literal, Optional
from scipy.optimize import brentq

from greeks import bs_price  # after WP1.3, this is BSM and supports q

OptionType = Literal["call", "put"]

def implied_vol_from_price(
    *,
    market_price: float,
    S: float,
    K: float,
    t: float,
    r: float,
    q: float,
    option_type: OptionType,
    vol_low: float = 1e-6,
    vol_high: float = 5.0,
) -> Optional[float]:
    """Return sigma (decimal) such that BSM price ~= market_price.
    Returns None if inputs invalid or no root is bracketed.
    """
    if market_price is None or market_price <= 0 or S <= 0 or K <= 0 or t <= 0:
        return None

    def f(sig: float) -> float:
        return bs_price(S, K, t, r, sig, option_type, q=q) - market_price

    try:
        f_low = f(vol_low)
        f_high = f(vol_high)
        # Need a sign change for brentq
        if f_low == 0:
            return vol_low
        if f_high == 0:
            return vol_high
        if f_low * f_high > 0:
            return None
        return float(brentq(f, vol_low, vol_high, maxiter=200))
    except Exception:
        return None
```

#### Use the solver in chain processing
Modify `backend/data_provider/yfinance_provider.py::get_options_chain()`:
1. Compute `t_years = time_utils.year_frac_to(expiration)`
2. Compute `r = default_risk_free_rate(provider)` (or cached)
3. Compute `q` from quote dividend yield (or 0)
4. For each option row:
   - compute `mid` if bid/ask valid else last
   - if yfinance IV is missing/NaN:
     - call `implied_vol_from_price(market_price=mid, S=price, K=strike, t=t_years, r=r, q=q, option_type=...)`
     - if sigma returned, set:
       - `iv_decimal = sigma`
       - `iv_pct = sigma * 100`
       - add `iv_source = "solved"`
     - else:
       - leave IV null and set `iv_source = "missing"`
   - if yfinance IV exists:
     - `iv_source = "chain"`

Return `iv_source` (optional) so UI can flag low-quality rows.

#### Tests
Add `backend/tests/test_iv_solver.py`:
- Generate a known BSM price from sigma=0.25, then solve and assert ~0.25 within 1e-4.
- Include both call and put tests.
- Include a “no bracket” test where market_price is impossible and solver returns None.

---



### 1.6 Add a shared “Assumptions” endpoint (single source of default r/q/day-count)

To prevent frontend/backends from drifting (and to keep numbers reproducible), add an endpoint that returns the backend’s current default assumptions (especially `r` derived from ^TNX).

#### Files to add
- `backend/routes/assumptions.py`

#### Endpoint
`GET /api/assumptions`

Response example:
```json
{
  "as_of": "2026-02-22T15:30:00-05:00",
  "risk_free_rate": 0.0445,
  "risk_free_source": "^TNX",
  "tnx_yield_percent": 4.45,
  "dividend_yield_default": 0.0,
  "day_count": "ACT/365",
  "default_pricing_mode": "mid",
  "default_slippage_pct_of_spread": 0.0
}
```

Implementation notes:
- Use `default_risk_free_rate(provider)` from `backend/assumptions.py` (with caching).
- `as_of` should be `time_utils.now_et().isoformat()`.

#### Frontend usage (accuracy)
- In `frontend/src/components/Analysis.jsx` (or a global app store), fetch `/api/assumptions` once on load.
- Pass `risk_free_rate` into:
  - strategy analysis calls
  - greeks calls (if used)
  - any probability calculations
- Display the assumptions somewhere in the Analysis UI so users know what model inputs were used.

---

## WP2 — Backend Strategy Analytics Engine (the core of upgrade #1)

### 2.1 Add canonical strategy analysis module

#### Files to add (new package)
- `backend/strategy_engine/__init__.py`
- `backend/strategy_engine/models.py`
- `backend/strategy_engine/payoff.py`
- `backend/strategy_engine/pricing.py`
- `backend/strategy_engine/metrics.py`
- `backend/strategy_engine/curve.py`
- `backend/strategy_engine/probability.py` (optional if PoP)
- `backend/routes/strategy.py` (FastAPI router)

#### 2.1.1 Data models (backend)
In `backend/strategy_engine/models.py` define Pydantic models (exact fields):

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

Instrument = Literal["option", "stock"]
OptionType = Literal["call", "put"]
Action = Literal["buy", "sell"]

class Underlying(BaseModel):
    symbol: Optional[str] = None
    price: float
    dividend_yield: float = 0.0  # decimal
    as_of: Optional[str] = None  # ISO datetime string (optional)

class PricingAssumptions(BaseModel):
    risk_free_rate: float  # decimal
    dividend_yield: float = 0.0  # default if not supplied per-underlying
    model: Literal["BSM"] = "BSM"
    day_count: Literal["ACT/365"] = "ACT/365"

class StrategyLeg(BaseModel):
    instrument: Instrument
    action: Action
    quantity: float  # contracts for options, shares for stock (allow float for partial)
    # Stock fields
    entry_price: float  # per share
    # Option fields
    option_type: Optional[OptionType] = None
    strike: Optional[float] = None
    expiration: Optional[str] = None  # YYYY-MM-DD
    iv: Optional[float] = None  # decimal (0.30)
    multiplier: int = 100  # default
    bid: Optional[float] = None
    ask: Optional[float] = None
    # If frontend wants to send a specific entry fill price separate from mark:
    entry_price_override: Optional[float] = None
```

Notes:
- For stock legs: `instrument="stock"`, `option_type/strike/expiration/iv` must be None.
- For option legs: `instrument="option"`, require option_type/strike/expiration.

#### 2.1.2 Core sign normalization
In `backend/strategy_engine/payoff.py` implement:

```python
def signed_qty(leg: StrategyLeg) -> float:
    return leg.quantity if leg.action == "buy" else -leg.quantity
```

For options, this yields signed contracts; for stock, signed shares.

#### 2.1.3 Expiration payoff (exact, deterministic)
Implement:

```python
def payoff_at_expiration(leg: StrategyLeg, S: float) -> float:
    q = signed_qty(leg)
    if leg.instrument == "stock":
        return q * (S - leg.entry_price)
    # option:
    assert leg.option_type and leg.strike is not None
    intrinsic = max(0.0, S - leg.strike) if leg.option_type == "call" else max(0.0, leg.strike - S)
    # entry_price is premium per share
    return q * leg.multiplier * (intrinsic - leg.entry_price)
```

Total strategy payoff is sum across legs.

This must exactly match the payoff definitions already tested in `backend/test_strategy_math.py`.

#### 2.1.4 Mark-to-market valuation at an evaluation date
In `backend/strategy_engine/pricing.py` implement:

- `def option_model_price(S, K, t, r, q, sigma, option_type) -> float:`
  - call `greeks.bs_price(..., q=q)` (after WP1 updates) or implement locally.
- `def leg_value(leg, S, eval_dt, assumptions) -> float:`
  - stock: `q_shares * S`
  - option:
    - compute `t = year_frac_to(leg.expiration, as_of=eval_dt)`
    - if `t == 0`: value = intrinsic
    - else require `sigma` (leg.iv). If missing, compute via IV solver (WP1.5) or default to underlying ATM IV (documented).
    - value = model_price
  - return **position value in dollars**: `signed_qty * multiplier * model_price` for options; `signed_qty * S` for stock.

Also implement:
- `def leg_entry_cost(leg: StrategyLeg) -> float:`
  - stock: `signed_qty * leg.entry_price` (this is dollars spent; positive if buy? careful)
  - options: `signed_qty * leg.multiplier * leg.entry_price`
But be explicit: store both:
  - `entry_cashflow = -signed_qty * ... * entry_price` (cashflow sign)
  - `entry_cost_basis = signed_qty * ... * entry_price` (position basis)
Choose one convention and stick to it everywhere.

Recommended convention:
- `entry_cashflow`:
  - BUY -> negative (cash paid)
  - SELL -> positive (cash received)
  - `entry_cashflow = -signed_qty * units * entry_price`
- `current_value`:
  - long value positive, short value negative
  - `current_value = signed_qty * units * current_price`
- Then:
  - `pnl = current_value + entry_cashflow`
    - because if you paid cash (negative), pnl increases when current_value rises.
Check: long call buy 1 @ 2.00, now 3.00:
  - signed_qty=+1, entry_cashflow=-200, current_value=+300, pnl=100 correct.
Short call sell 1 @ 2.00, now 3.00:
  - signed_qty=-1, entry_cashflow=+200, current_value=-300, pnl=-100 correct.

Implement this exactly.

---

### 2.2 Exact expiration metrics (max profit/loss, breakevens, capital)

#### 2.2.1 Breakevens (exact, not grid search)
In `backend/strategy_engine/metrics.py`:

Algorithm (for expiration payoff):
1. Collect breakpoints:
   - `points = sorted({0.0} ∪ {strike for each option leg})`
   - Add `hi = max(max_strike*3, underlying_price*3, 1.0)` as a finite proxy for “very high”.
2. Evaluate payoff at each point and at `hi`.
3. For each adjacent segment `[x0,x1]`:
   - payoff is linear (expiration payoff is piecewise linear)
   - if `y0 == 0`, record `x0`
   - if `y0*y1 < 0` or `y1 == 0`, solve root by linear interpolation:
     - `x = x0 + (0 - y0) * (x1 - x0) / (y1 - y0)`
4. Deduplicate roots within 1e-6 and round for display only in UI.

This yields **exact** breakevens given linear segments.

#### 2.2.2 Max profit/loss (correctly detect unbounded)
Compute slope as S→∞:
- `slope_inf = net_shares + 100*net_call_contracts`
  - `net_shares = sum(signed_qty for stock legs)`
  - `net_call_contracts = sum(signed_qty for call option legs)`
- If `slope_inf > 0`: `max_profit = +inf`
- If `slope_inf < 0`: `max_loss = -inf`
- Else bounded; evaluate payoff at all breakpoints + `hi` and take min/max.

Also always evaluate at `S=0` (or epsilon) because puts behave differently at 0:
- Use `S_low = 0.0` (intrinsic uses max(K-S,0) so safe).
- Evaluate at `0.0` and at each strike, and at `hi`.

#### 2.2.3 Capital required (fixes major current inaccuracies)
Define `capital_required` as:
- If `max_loss` is finite: `capital_required = abs(max_loss)`  
  (this matches defined-risk options spreads and long options)
- If `max_loss` is infinite: `capital_required = None` + provide `margin_note`
  - do **not** pretend it’s `abs(net_premium)` (current frontend bug).
- For stock legs:
  - long stock requires capital `shares * entry_price` (cash outlay) if no margin
  - but if tool does not model margin, use:
    - `capital_required = abs(min_payoff)` at S=0? Not correct for stock.
Better:
  - If any stock leg exists, set:
    - `capital_required_stock = max(0, -entry_cashflow_stock)` (cash paid to buy shares)
  - Then total required is:
    - `capital_required = capital_required_stock + capital_required_options_defined_risk`
For now, simplest conservative rule:
  - `capital_required = max(0, -total_entry_cashflow)` **only** for strategies where max loss is infinite?  
  - But for defined-risk strategies, `abs(max_loss)` is better.

Implement:
- `capital_required = abs(max_loss)` if `max_loss` finite.
- Else if infinite:
  - `capital_required = max(0, -total_entry_cashflow)` (cash outlay) and set `requires_margin=True`.

Return both fields:
- `capital_required`
- `requires_margin` (bool)
- `capital_method` (string enum explaining which rule was used)

#### 2.2.4 Risk/Reward
- If max_profit is infinite and max_loss finite: risk/reward is not a single scalar. Return:
  - `risk_reward = None`
  - `risk_reward_note = "Unlimited max profit"`
- Else if both finite and `capital_required > 0`:
  - `risk_reward = max_profit / capital_required` (use absolute values carefully; max_profit positive, capital positive)
- For credit strategies where max_profit is the credit, it’s fine.

---

### 2.3 Strategy payoff curves (expiration + mark-to-market)

In `backend/strategy_engine/curve.py`:

#### Price grid generation (deterministic)
Implement:
- `def default_price_grid(S0, strikes, points=200) -> (price_min, price_max, grid):`
  - `min_strike = min(strikes)` if strikes else S0
  - `max_strike = max(strikes)` if strikes else S0
  - `padding = max(0.15*S0, 1.5*(max_strike-min_strike or 0.2*S0))`
  - `price_min = max(0, min_strike - padding)`
  - `price_max = max_strike + padding`
  - `grid = linspace(price_min, price_max, points)`
- Use `numpy.linspace` to avoid accumulating float error.

#### Expiration curve
- `curve_exp = [{"price": p, "pl": strategy_payoff_at_expiration(legs,p)} ...]`

#### MTM curve at eval date + days_forward
- `eval_dt = now_et() + timedelta(days=days_forward)` (timezone-aware)
- Value each option leg using `t = year_frac_to(exp, as_of=eval_dt)`
- For legs already expired by eval_dt: treat as intrinsic
- P&L at eval date:
  - `pnl = total_current_value + total_entry_cashflow`

Return both curves.

---

### 2.4 New API endpoint: `/api/strategy/analyze`

#### Files to add/modify
- Add `backend/routes/strategy.py`
- Update `backend/main.py` to include the router:
  - `from routes.strategy import create_strategy_routes`
  - `app.include_router(create_strategy_routes(provider))`

#### Endpoint contract
`POST /api/strategy/analyze` request body:

```json
{
  "underlying": { "symbol": "AAPL", "price": 190.12, "dividend_yield": 0.005 },
  "assumptions": { "risk_free_rate": 0.045, "dividend_yield": 0.005, "model": "BSM" },
  "legs": [
    {
      "instrument": "option",
      "option_type": "call",
      "action": "buy",
      "quantity": 1,
      "strike": 200,
      "expiration": "2026-03-20",
      "iv": 0.28,
      "multiplier": 100,
      "entry_price": 3.25
    }
  ],
  "pricing_mode": "mid", 
  "slippage_pct_of_spread": 0.0,
  "curve_points": 200,
  "days_forward": 0
}
```

Notes:
- If `assumptions` is omitted or missing fields, backend must fill defaults using `GET /api/assumptions` logic (r from ^TNX, day_count default) and `underlying.dividend_yield` for q.

- `pricing_mode` and `slippage_pct_of_spread` are used to compute *entry_price* if `entry_price_override` not provided and bid/ask are present (WP5). If frontend already computed entry, backend can just trust `entry_price`.
- `assumptions.dividend_yield` is the default q; leg-level q is not needed.

Response:

```json
{
  "underlying_price": 190.12,
  "assumptions_used": { "risk_free_rate": 0.045, "dividend_yield": 0.005, "model": "BSM", "day_count": "ACT/365" },
  "entry_cashflow": -325.0,
  "net_premium": -325.0,
  "capital_required": 325.0,
  "requires_margin": false,
  "max_profit": null, 
  "max_loss": -325.0,
  "breakevens": [203.25],
  "risk_reward": null,
  "curves": {
    "expiration": [ { "price": 150.0, "pl": -325.0 }, ... ],
    "mtm": [ { "price": 150.0, "pl": -200.1 }, ... ]
  },
  "pop": { "value": 42.1, "model": "lognormal_risk_neutral", "as_of": "...", "horizon": "earliest_expiration" },
  "data_quality": { "missing_iv_legs": 0, "iv_source": "chain", "mark_source": "mid" }
}
```

Rules:
- Use `null` for infinite max_profit/max_loss, not `Infinity` (JSON compatibility).
- `net_premium` should equal `entry_cashflow` for options-only strategies; for stock legs it includes stock cashflow too, so keep both:
  - `entry_cashflow_total`
  - `entry_cashflow_options`
  - `entry_cashflow_stock`

---

### 2.5 Remove/replace incorrect existing endpoint
`backend/routes/market.py::/greeks/payoff-curve` currently sums theoretical option prices without buy/sell/qty/entry cost. This is numerically incorrect and should not exist in current form.

Do one of:
- **Delete** `/greeks/payoff-curve` entirely (preferred).
- Or rewrite it to accept `StrategyLeg` objects and return P&L curves using the new engine.

---

## WP3 — Frontend: Replace all client-side math with `/api/strategy/analyze` (upgrade #1 completion)

### Files to modify
- `frontend/src/components/PayoffDiagram.jsx`
- `frontend/src/components/StrategyComparison.jsx`
- `frontend/src/api/client.js`
- Potentially `frontend/src/components/Analysis.jsx` to pass assumptions

### 3.1 Add API client function
In `frontend/src/api/client.js` add:

```js
export function analyzeStrategy(payload) {
  return requestPost('/strategy/analyze', payload);
}
```

### 3.2 Refactor `PayoffDiagram.jsx`
**Delete/stop using**:
- JS `normCDF`, `bsPrice`, `legPayoff`, `legPreExpPL`, `findBreakevens`, `estimateProbOfProfit`, and `analyzeStrategy` computations.

New flow:
1. Component receives:
   - `legs` (from StrategyBuilder)
   - `quote` (underlying price, dividend_yield if available)
   - `assumptions` (risk_free_rate, pricing_mode, etc.) stored in Analysis page state
2. Build payload:
   - Convert UI legs into backend `StrategyLeg` schema:
     - options: map `type: "Call"/"Put"` -> `option_type: "call"/"put"`
     - premium -> `entry_price`
     - iv in UI is percent; convert to decimal: `iv/100`
     - include bid/ask if present
   - underlying:
     - `price = quote.price`
     - `dividend_yield = quote.dividend_yield ?? 0`
   - assumptions:
     - `risk_free_rate` from UI settings (default from backend if you expose)
     - `dividend_yield` same as underlying
3. Call `analyzeStrategy(payload)` whenever:
   - legs change
   - days_forward slider changes
   - pricing mode changes
4. Render:
   - expiration curve: `data.curves.expiration`
   - mtm curve: `data.curves.mtm`
   - metrics: `max_profit`, `max_loss`, `breakevens`, `capital_required`, `net_premium`, `pop`

Important UI changes for accuracy:
- Replace current `totalCapital = abs(netPremium)` with backend `capital_required`.
- If backend returns `requires_margin=true`, show “Margin required / undefined risk” badge and don’t show ROI metrics that assume defined capital.

### 3.3 Refactor `StrategyComparison.jsx`
- Remove imports `analyzeStrategy, strategyPayoff` from PayoffDiagram.
- For each slot, call backend `analyzeStrategy` and merge curves by price.
- Use `capital_required` and backend metrics, not recomputed ones.

### 3.4 Ensure UI formatting only (no rounding in math)
- In UI, format money to 2 decimals.
- Display unlimited as “Unlimited”.
- For PoP, show “Model-based” label with tooltip describing lognormal assumption.

---

## WP4 — Market Data Caching + Backend Strike Filtering (upgrade #2)

### 4.1 Add a simple TTL cache (no new dependencies)

#### Files to add
- `backend/cache.py`

Implement:
```python
import time
from typing import Any

class TTLCache:
    def __init__(self, ttl_seconds: float):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if not item:
            return None
        ts, val = item
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, val: Any) -> None:
        self._store[key] = (time.time(), val)
```

### 4.2 Apply caching to yfinance provider
Modify `backend/data_provider/yfinance_provider.py`:
- Create caches on provider instance:
  - `quote_cache = TTLCache(5)`  # seconds (tune)
  - `chain_cache = TTLCache(15)` # seconds
  - `history_cache = TTLCache(60)` # seconds
  - `tnx_cache = TTLCache(60)` # seconds
- Wrap calls:
  - `get_quote`, `get_quote_light`, `get_options_chain`, `get_history`, `get_options_expirations`

**Accuracy note:** TTL caching is fine as long as:
- TTLs are short for quotes/chains.
- Add `force_refresh` query param for endpoints where user needs newest.

### 4.3 Backend strike filtering (reduce payload + compute fewer Greeks)
Modify `backend/routes/market.py::get_chain` to accept optional query params:
- `strike_range_pct` (float, e.g., 0.2 for ±20%)
- OR `min_strike` and `max_strike`

Backend should:
1. Fetch chain.
2. Determine S0 = chain["underlying_price"].
3. Filter calls/puts to strikes within bounds.
4. Return only filtered arrays.

Then update frontend `OptionsChain.jsx`:
- Instead of filtering client-side, request:
  - `/options/chain/{symbol}?expiration=...&strike_range_pct=0.2`
- Keep UI slider, but it controls the param.

### 4.4 Remove rounding in provider outputs
- Return raw floats; UI already formats toFixed.

---

## WP5 — Execution-Realistic Pricing + Liquidity (upgrade #5)

### 5.1 Add a pricing mode concept (shared by UI + backend)
Pricing modes:
- `"mid"`: (bid+ask)/2 if both present else last
- `"conservative"`:
  - buys use ask
  - sells use bid
  - fallback to last if side quote missing
- `"mid_slippage"`:
  - buys: mid + slippage_pct*spread
  - sells: mid - slippage_pct*spread
  - clamp within [bid, ask] when both exist

#### Backend implementation
In `backend/strategy_engine/pricing.py` implement:

```python
def mark_price(bid, ask, last) -> float | None:
    ...

def entry_fill_price(action, bid, ask, last, mode, slippage_pct) -> float | None:
    ...
```

Rules (exact):
- If bid and ask are both > 0:
  - mid = (bid+ask)/2
  - spread = ask-bid
  - conservative:
    - buy -> ask
    - sell -> bid
  - mid_slippage:
    - buy -> mid + slippage_pct*spread
    - sell -> mid - slippage_pct*spread
- Else:
  - use last if >0 else None

Use these for:
- computing entry_price if `entry_price_override` is None AND bid/ask exist
- computing current mark value if you want mark-based P&L (optional for strategy builder; required for portfolio marks)

### 5.2 Liquidity scoring and filters (recommender + optional UI)
Replace `_liquid()` in `backend/routes/recommender.py` with a score:

Inputs:
- bid, ask, last_price
- open_interest
- volume

Compute:
- `mid = (bid+ask)/2` if possible
- `spread_pct = (ask-bid)/mid` if mid>0
Rules:
- Reject if:
  - bid<=0 or ask<=0 (unless last is used AND you mark as low quality)
  - spread_pct > 0.20 (20%) (tunable)
  - open_interest < 25 AND volume < 10 (tunable)
Return:
- `liquidity_score` in [0,100] where:
  - tighter spreads, higher OI/vol => higher score
Store on each option dict if helpful.

Recommender must:
- filter low liquidity before constructing strategies
- prefer higher-liquidity legs when multiple candidates tie

### 5.3 Ensure strategy analysis uses the same entry/mark convention as recommender
- The recommender should not compute payoff with mid while analysis uses conservative (or vice versa).
- Add to recommender request (frontend):
  - pricing_mode + slippage
- Pass it through to backend.

---

## WP6 — Portfolio: Correct Day P&L + Mark History + SQLite Persistence (upgrade #3)

### 6.1 Replace JSON persistence with SQLite (accuracy + consistency)
JSON files are prone to corruption and don’t support mark history reliably.

#### Files to add
- `backend/db.py`
- `backend/repositories/portfolio_repo.py`
- `backend/repositories/watchlist_repo.py`
- `backend/repositories/marks_repo.py`
- `backend/repositories/alerts_repo.py` (optional)

#### Schema (SQLite)
Create tables:

1) `positions`
- `id TEXT PRIMARY KEY`
- `ticker TEXT NOT NULL`
- `asset_type TEXT NOT NULL`  # stock/call/put
- `quantity REAL NOT NULL`
- `avg_cost REAL NOT NULL`    # entry price per share (stock) or per option share
- `strike REAL`
- `expiration TEXT`           # YYYY-MM-DD
- `created_at TEXT NOT NULL`  # ISO datetime
- `updated_at TEXT NOT NULL`

2) `marks`
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `as_of_date TEXT NOT NULL`  # YYYY-MM-DD (ET trading date)
- `as_of_ts TEXT NOT NULL`    # ISO datetime
- `ticker TEXT NOT NULL`
- `asset_type TEXT NOT NULL`
- `strike REAL`
- `expiration TEXT`
- `mark_price REAL NOT NULL`  # per share for stock or option
- `mark_source TEXT NOT NULL` # mid/bid/ask/last
- unique index on (as_of_date, ticker, asset_type, strike, expiration)

3) `watchlist`
- `ticker TEXT PRIMARY KEY`

4) `alert_thresholds`, `dismissed_alerts` (mirror existing JSON behavior)

### 6.2 Migration logic
On startup (in `backend/main.py`):
- If DB is empty AND `backend/data/portfolio.json` exists:
  - load JSON positions
  - insert into DB
- same for watchlist/alerts.

### 6.3 Fix options day P&L (must be correct)
**Problem today:** options day_pnl is computed vs avg_cost, which is total P&L, not day.

Correct method:
1. Determine today’s ET trading date `D0`.
2. Determine prior trading date `D1` (skip weekends; optionally holiday calendar later).
3. For each position, get:
   - current mark price (today)
   - prior mark price (D1) from marks table
4. Day P&L:
   - Stock: `(px_today - px_prior) * shares`
   - Option: `(opt_mark_today - opt_mark_prior) * contracts * 100`
5. If prior mark missing:
   - set day_pnl = None and mark as `"day_pnl_unavailable": true` (do NOT fake it with avg_cost)

Implement in `backend/portfolio_enrichment.py` (or a new `portfolio_service.py`):
- On each `/portfolio/enriched` call:
  - compute marks for all positions and insert/update today’s mark row
  - compute day P&L using prior mark if available

### 6.4 Compute portfolio day_pnl_percent correctly
- `prev_value = sum(position_value_using_prior_marks)`
- `day_pnl_percent = day_pnl / prev_value * 100` if prev_value != 0

### 6.5 Ensure mark price definition is explicit
For options, mark price should be:
- mid if bid/ask valid
- else last
Store `mark_source` per mark.

---

## WP7 — Portfolio Risk Additions: Correlation, Beta, Stress Tests (upgrade #6)

### 7.1 Correlation risk
#### Backend
- Create `backend/risk_metrics.py` with:
  - `compute_return_series(provider, tickers, lookback="6mo")`
  - `compute_correlations(returns_df) -> list[{ticker_a, ticker_b, corr, window}]`
- Use daily close returns.
- Use aligned dates (inner join).
- Return top N correlated pairs (abs(corr) highest), with threshold flag (e.g., abs>0.8).

#### Frontend
- `frontend/src/components/PortfolioCharts.jsx` or new `CorrelationPanel.jsx`
  - Display top correlated pairs with correlation and lookback window.

### 7.2 Realized beta vs SPY
Compute:
- For each ticker: `beta = cov(r_i, r_spy) / var(r_spy)` over lookback (e.g., 90 trading days)
- Portfolio beta:
  - weight by **dollar exposure** (stock market value + options dollar delta if you want)
  - simplest: weight by market value of stock holdings only (document)

Return:
- `beta_realized_portfolio`
- optionally per-position realized beta

### 7.3 Stress tests
Compute portfolio P&L approximation for ±2%, ±5% market moves:
- Use portfolio dollar delta + gamma:
  - `dS = move_pct * S` (for SPY or per holding; approximate using portfolio beta-weighted delta vs SPY)
Simpler:
- Use current portfolio delta_dollars as already defined:
  - `pnl ≈ delta_dollars * move_pct + 0.5 * gamma_shares * (S*move_pct)^2`
Return a small table:
- move_pct: -5, -2, +2, +5
- pnl_est

Display in dashboard.

---

## WP8 — Stock Legs in Strategy Builder + Engine Support (upgrade #4)

### 8.1 Frontend: allow adding stock legs
Modify `frontend/src/components/StrategyBuilder.jsx`:
- Add a new “Add Stock Leg” button.
- Stock leg form fields:
  - action: buy/sell
  - shares: default 100 (for covered call template)
  - entry_price: default current underlying price (or allow manual)
- Store stock leg in the same `legs` array with a new shape:
  - `{ instrument: 'stock', action, quantity, entry_price }`

### 8.2 Update templates
- Covered Call template must create:
  - Stock: BUY 100 shares @ current price
  - Call: SELL 1 OTM call (same expiry)
- Collar template (optional) should create:
  - Stock: BUY 100
  - Put: BUY 1 OTM put
  - Call: SELL 1 OTM call

### 8.3 Backend: strategy engine must accept stock legs
This is already in WP2 models/payoff/pricing.

### 8.4 UI display
Update `PayoffDiagram` and any legs table to show stock legs clearly:
- “BUY 100 Shares @ 190.12”
- No strike/expiry/IV columns.

---

## WP9 — Recommender: Align with canonical pricing + metrics (upgrade #1 + #5)

### 9.1 Make recommender use the same payoff/metrics code
Modify `backend/routes/recommender.py`:
- Replace `_leg_pl`, `_payoff_curve`, and per-strategy metric calculations with calls into:
  - `strategy_engine.payoff.payoff_at_expiration`
  - `strategy_engine.metrics` for capital/max loss/breakeven
- Recommender still can generate candidate legs the same way, but once it has legs it should call canonical metrics.

### 9.2 Use pricing_mode for premiums
- Replace `_mid(opt)` with `entry_fill_price(...)` using pricing_mode and slippage.
- Make frontend recommender UI expose:
  - pricing mode dropdown
  - optional slippage slider
- Pass those into recommend request.

### 9.3 Ensure capital_required is correct
- For spreads, capital required should match max loss.
- For naked options, return `requires_margin=true` and avoid ranking purely by (payoff/capital) unless you define a margin model.

---

# FINAL “Definition of Done” (must pass)

1. **All payoff math** matches deterministic formulas (existing test suite + new pytest suite).
2. **No client-side pricing/payoff logic** affects displayed metrics; frontend uses backend analysis.
3. **Time-to-expiry is correct intraday** (expiration-day options still have time value until close).
4. **Risk-free rate is not off by 10×** (TNX scaling fixed; backend uses decimal).
5. **Dividend yield is included** in all pricing/Greeks (q in BSM).
6. **Capital required is correct** for debit/credit spreads and not faked for margin products.
7. **Options day P&L is correct** (vs prior mark, not avg_cost).
8. **All numeric outputs have tests** and tests run green.

---

## Appendix: Known current numeric accuracy bugs to explicitly fix

- `frontend/src/components/PayoffDiagram.jsx`: `totalCapital = abs(netPremium)` is incorrect for credit spreads and many strategies.
- `frontend/src/components/PayoffDiagram.jsx`: PoP is computed with a rough heuristic and average IV; must be replaced by backend canonical PoP (or labeled clearly).
- `backend/portfolio_enrichment.py`: options `day_pnl` uses `(option_price - avg_cost)` which is total P&L, not day.
- `backend/data_provider/yfinance_provider.py` and `backend/portfolio_enrichment.py`: time to expiry uses date-only diff → 0 on expiry day.
- `frontend/src/components/MarketOverviewBar.jsx`: TNX shown as `%` without scaling; likely off by 10×.



---

## Appendix B: Optional advanced modeling upgrades (only if you want closer “broker-like” theoretical values)

These are **not required** to fix the current correctness bugs, but they improve theoretical pricing realism.

### B1) American option pricing (early exercise) for equity options
- Equity options are American-style; Black‑Scholes‑Merton is European.
- Differences matter most for:
  - deep ITM puts
  - call options on dividend-paying stocks near ex-dividend dates

Implementation option (recommended if you do this):
- Add `backend/american_pricing.py` implementing a Cox–Ross–Rubinstein (CRR) binomial tree:
  - price: backward induction with early exercise check
  - delta/gamma/theta: compute from the tree (standard finite-difference extraction)
- Add a toggle in assumptions: `model = "BSM" | "CRR_BINOMIAL"`

Accuracy requirement if implemented:
- Add tests comparing prices to a known reference (QuantLib or a trusted external calculator) for at least:
  - ITM put with dividends
  - ITM call with dividends (where early exercise can be optimal)
- Do not ship this without tests; wrong American pricing is worse than consistent BSM.

### B2) Discrete dividends / ex-dividend modeling
- Continuous q is an approximation.
- If you need more precision:
  - pull dividend schedule (date + amount)
  - adjust spot or forward in pricing

### B3) Volatility surface / smile
- Current approach uses a single IV per leg; real options have skew/smile.
- If you want improved “market-consistent” curves:
  - interpolate IV across strikes/expirations
  - price each point on the curve with strike-specific IV

