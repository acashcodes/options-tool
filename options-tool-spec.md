# Akash Pre-Revenue Fund — Options Strategy Analyzer
## Product Spec v1.0

---

## Overview

A locally-hosted web application for pre-trade options analysis. The user enters a stock/ETF ticker and the app pulls live options data via yfinance, enabling strategy building, payoff visualization, and an AI-powered strategy recommender.

**Tech Stack:**
- **Frontend:** React (with Vite) — single-page app with dark Bloomberg-terminal-inspired theme
- **Backend:** Python (Flask or FastAPI) — handles yfinance data fetching and computations
- **Charts:** Recharts or Plotly.js for interactive payoff diagrams
- **Local hosting:** Runs on localhost:3000 (frontend) and localhost:8000 (backend API)

---

## Design Direction

- **Theme:** Dark mode, Bloomberg/professional terminal aesthetic
- **Color palette:** Near-black backgrounds (#0a0a0f, #12121a), with electric accent colors — cyan/teal (#00d4aa) for profit, red/coral (#ff4757) for loss, muted grays for secondary text
- **Typography:** Monospace or semi-mono for data (JetBrains Mono or IBM Plex Mono), clean sans-serif for labels (IBM Plex Sans or similar)
- **Layout:** Single scrollable page with clearly defined sections, subtle borders/dividers, generous spacing
- **Data density:** High — this is a power tool, not a consumer app. Tables should be compact but readable
- **Charts:** Clean gridlines, glow effects on profit/loss curves, interactive hover tooltips

---

## App Navigation

Top-level tab bar across the top of the page (like browser tabs). Two tabs:
- **📊 Dashboard** — Portfolio, watchlist, market overview, alerts
- **🔬 Analysis** — Ticker research, options chain, strategy builder, recommender

The app opens to the Dashboard tab by default. The tab bar is always visible at the top. Clicking a ticker anywhere in the Dashboard (from holdings, watchlist, or alerts) should navigate to the Analysis tab with that ticker pre-loaded.

---

## TAB 1: DASHBOARD (Homepage)

A scrollable page with the following sections:

### Section 1A: Market Overview Bar (Top of Dashboard)
A compact horizontal bar showing key market indicators at a glance:
- **SPY** — price + daily % change
- **QQQ** — price + daily % change
- **VIX** — current level + daily change (color-coded: green if low/calm, yellow if elevated, red if high)
- **10Y Treasury Yield** — current yield + daily change
- **Fear & Greed indicator** (optional — can be derived from VIX level: <15 = Extreme Greed, 15-20 = Greed, 20-25 = Neutral, 25-30 = Fear, 30+ = Extreme Fear)
- Auto-refreshes periodically (or on page load)

### Section 1B: Portfolio Dashboard
The user's "command center" for their positions.

**Portfolio Input Methods (accessible via a "Manage Portfolio" button/modal):**
- **Manual entry:** A form where the user types in positions (ticker, quantity, avg cost, option details if applicable)
- **Screenshot ingestion:** User uploads a screenshot from Robinhood (or other broker). The backend uses OCR (via pytesseract or a vision API) to extract position data. Because OCR can be imprecise, always show the parsed results and let the user confirm/edit before saving.
- **CSV upload:** User can upload a CSV with columns: ticker, type (stock/call/put), quantity, avg_cost, strike (if option), expiry (if option)
- **Claude-assisted entry (future):** Placeholder for a chat interface where the user describes positions and they get parsed into structured data
- **Persistence:** Portfolio data is saved to a local JSON file so it persists between sessions

**Portfolio-Level Metrics Bar** (prominent cards/tiles at top of section):
- **Total Portfolio Value** (sum of all market values)
- **Total P&L** ($ and %)
- **Gross Exposure** (sum of absolute market values of all positions — important for leveraged portfolios)
- **Net Exposure** (long value minus short value)
- **Leverage Ratio** (Gross Exposure ÷ Net Liquidation Value — e.g., 198% means nearly 2x leveraged)
- **Long / Short breakdown** (total long value vs total short value)

**Portfolio Greeks** (aggregated across all option positions, displayed as a secondary metrics row):
- **Portfolio Delta** (net delta in dollar terms — "if the market moves 1%, my portfolio moves $X")
- **Portfolio Beta-Weighted Delta** (delta normalized to SPY — "my portfolio behaves like X shares of SPY")
- **Portfolio Theta** (total daily time decay — "I'm paying/earning $X per day in time value")
- **Portfolio Vega** (sensitivity to IV changes — "a 1% rise in IV changes my portfolio by $X")
- **Portfolio Gamma** (how fast delta changes)

**Holdings Table:**
- Columns: Ticker, Type (Stock/Call/Put), Quantity, Avg Cost, Current Price, Market Value, P&L ($), P&L (%), Weight (% of portfolio)
- For options: also show Strike, Expiry, Days to Expiry
- Color-coded P&L (green/red)
- Sortable by any column
- **Click any row → navigates to Analysis tab with that ticker pre-loaded**
- "Analyze Options" button on each equity row

**Portfolio Analytics** (below the holdings table):
- **Concentration chart:** Pie or bar chart showing position weights
- **Sector exposure** (map tickers to sectors using yfinance sector data)
- **Beta exposure:** Portfolio beta vs SPY
- **Correlation risk:** Flag if multiple holdings are highly correlated (e.g., SNAP + PINS + META are all social media)

### Section 1C: Watchlist
A separate table for tickers the user is tracking but does NOT hold.

**Watchlist Management:**
- Add/remove tickers via a simple input field + "Add" button
- Watchlist persists to local JSON file

**Watchlist Table Columns:**
- Ticker, Current Price, Daily Change ($ and %), IV Rank, IV Percentile, 52-Week High/Low, Next Earnings Date
- Sortable by any column
- **Click any row → navigates to Analysis tab with that ticker pre-loaded**

### Section 1D: Alerts & Flags
An automated alerts panel that scans portfolio holdings AND watchlist tickers and surfaces notable events:
- **Earnings alerts:** "[TICKER] earnings in X days" (flag anything within 7 days)
- **IV alerts:** "[TICKER] IV rank at Xth percentile" (flag if IV rank > 80 or < 20)
- **Expiration alerts:** "Your [TICKER] $X call expires in Y days" (flag options expiring within 7 days)
- **Large move alerts:** "[TICKER] moved X% today" (flag moves > 3%)
- Alerts are generated on page load based on current data, not a persistent notification system
- Each alert is clickable → navigates to Analysis tab for that ticker

---

## TAB 2: ANALYSIS

A scrollable page with the following sections, in linear flow:

### Section 2A: Ticker Input & Market Context Bar
- Large search bar at top: enter ticker symbol
- If user navigated here from Dashboard (clicked a holding or watchlist item), ticker is pre-filled
- On submit, display a context bar showing:
  - Current stock price (live)
  - Daily change ($ and %)
  - IV Rank (current IV vs. 52-week IV range, as a percentile)
  - IV Percentile
  - 52-week high/low
  - Earnings date (next upcoming, if available)
- This bar stays visible/sticky as user scrolls

### Section 2B: Options Chain Viewer
- Full options chain for the selected ticker
- **Filters:**
  - Expiration date selector (dropdown or horizontal tabs for each available expiry)
  - Strike range filter (e.g., show strikes within ±20% of current price, adjustable)
  - Toggle between Calls / Puts / Both side-by-side
- **Chain columns:** Strike, Last, Bid, Ask, Volume, Open Interest, IV, Delta, Gamma, Theta, Vega
- **Interaction:** Each row is clickable — clicking a call or put adds it as a leg to the Strategy Builder (Section 3)
- Highlight ITM vs OTM rows with subtle background color difference
- Highlight high-volume / high-OI strikes

### Section 2C: Strategy Builder
- Displays the legs the user has selected from the chain (or from templates)
- Each leg shows: Type (Call/Put), Strike, Expiration, Buy/Sell toggle, Quantity, Premium (bid/ask midpoint)
- User can:
  - Add legs manually (by clicking from chain)
  - Remove legs
  - Toggle any leg between Buy and Sell
  - Adjust quantity per leg
- **Strategy Templates dropdown:** Select from pre-built templates that auto-populate legs:
  - Long Call / Long Put
  - Covered Call (note: assumes stock ownership)
  - Bull Call Spread / Bear Put Spread
  - Bull Put Spread / Bear Call Spread
  - Long Straddle / Long Strangle
  - Short Straddle / Short Strangle
  - Iron Condor
  - Iron Butterfly
  - Calendar Spread
  - Custom (manual)
- When a template is selected, the app auto-selects reasonable default strikes based on the current chain (e.g., for an iron condor, it picks strikes around the current price with ~30 delta wings)
- **Net Debit/Credit** displayed prominently
- **"Analyze" button** — triggers payoff analysis below

### Section 2D: Payoff Analysis Dashboard
- Triggered after user clicks "Analyze" in the Strategy Builder
- **Payoff Diagram:**
  - X-axis: Stock price at expiration
  - Y-axis: Profit/Loss ($)
  - Line 1: Payoff at expiration (sharp, angular line — classic payoff diagram)
  - Line 2: Estimated payoff at current date / before expiration (smooth curve accounting for time value and IV)
  - Optional: Slider to adjust "days to expiration" and watch the curve morph from current to expiration
  - Shaded green region above breakeven, shaded red below
  - Vertical dashed line at current stock price
  - Breakeven points marked on x-axis
- **Summary Stats Panel** (next to or below the chart):
  - Max Profit ($ and %)
  - Max Loss ($ and %)
  - Breakeven price(s)
  - Probability of Profit (estimated using delta or normal distribution based on IV)
  - Risk/Reward Ratio
  - Net Premium Paid/Received
- **Greeks Summary** for the overall position:
  - Net Delta, Gamma, Theta, Vega
  - Brief plain-English interpretation (e.g., "Your position loses ~$12/day from time decay")

### Section 2E: Strategy Recommender
- **Input fields:**
  - Ticker (pre-filled from Section 1)
  - Target price (what you think the stock will hit)
  - Target date (by when)
  - Outlook direction: Bullish / Bearish / Neutral / High Volatility
- **On submit**, the engine:
  1. Pulls the relevant options chain data
  2. Scans through all viable strategy combinations (spreads, condors, straddles, etc.) for the expiration closest to the target date
  3. Ranks strategies by:
     - Probability of profit (given the target move)
     - Risk/reward ratio
     - Capital efficiency (max loss relative to max gain)
  4. Returns the top 3-5 recommended strategies
- **Each recommendation shows:**
  - Strategy name and legs (with specific strikes and expiry)
  - Payoff diagram (small/inline)
  - Key stats: max profit, max loss, breakeven, probability of profit
  - A one-line rationale (e.g., "Bull call spread offers capped upside but low capital requirement for your +15% target")
- **"Load into Strategy Builder" button** on each recommendation — sends the legs up to Section 3 for further analysis

### Section 2F: Strategy Comparison (Lower Priority)
- Side-by-side comparison of two strategies
- User can save strategies from the builder into Slot A and Slot B
- Shows both payoff diagrams overlaid on the same chart
- Comparison table of key metrics

---

## Data & Computation Notes

### Data Source Roadmap
- **Phase 1 (Current):** Use yfinance for all market data. Free, no API key needed, sufficient for development and personal use.
- **Phase 2 (Future):** Migrate to Charles Schwab Trader API once the user obtains API access. This will provide real-time data, account-level integration, and potentially order placement. The backend should be architected with a **data provider abstraction layer** — a common interface that yfinance implements now, and Schwab API can swap into later without rewriting the frontend or computation logic.
- **Architecture note:** All data fetching should go through a single `DataProvider` class with methods like `get_quote()`, `get_options_chain()`, `get_history()`. The yfinance implementation is the default. A Schwab implementation can be added later as a drop-in replacement.

### yfinance Data
- `yfinance.Ticker(symbol).options` — gets available expiration dates
- `yfinance.Ticker(symbol).option_chain(date)` — gets calls and puts DataFrames
- Fields available: strike, lastPrice, bid, ask, volume, openInterest, impliedVolatility
- Greeks (delta, gamma, theta, vega) are NOT provided by yfinance — must be calculated using Black-Scholes model with the IV from yfinance
- Current price: `yfinance.Ticker(symbol).info['currentPrice']` or `.history(period='1d')`

### Greeks Calculation
- Use Black-Scholes model to compute delta, gamma, theta, vega from:
  - Stock price, strike, time to expiry, risk-free rate (~5% or pull from treasury yield), IV from yfinance
- Python libraries: `scipy.stats.norm` for cumulative normal distribution, or use `mibian` or `py_vollib` packages

### Greeks Stress Testing (CRITICAL — Must Pass Before Moving On)
After implementing Greeks, run a comprehensive validation suite before proceeding to any other features:

1. **Benchmark against known values:** For a set of test cases (e.g., AAPL ATM call with 30 DTE), compute delta/gamma/theta/vega and compare against values shown on a broker platform (Schwab, IBKR, or options calculators like optionsprofitcalculator.com). Document the comparison.

2. **Boundary condition tests:**
   - Deep ITM call: delta should be ~1.0, theta near zero
   - Deep OTM call: delta should be ~0.0, theta near zero
   - ATM call at expiration (0 DTE): delta should be ~0.5, gamma should spike, theta should be very large negative
   - Very long-dated option (1+ year): theta should be small, vega should be large
   - Put-call parity: verify that call delta - put delta ≈ 1.0 for same strike/expiry

3. **Sensitivity checks:**
   - Increase IV by 1% → vega should predict the price change accurately
   - Move stock price by $1 → delta should predict the option price change accurately
   - Advance 1 day → theta should predict the price change accurately

4. **Cross-validation:** Compare computed Greeks against at least one other Python library (e.g., `mibian` or `py_vollib`) to verify implementation

5. **Output:** Generate a test report (printed to console or saved as a file) showing all test cases, expected vs. actual values, and PASS/FAIL status. All tests must pass before proceeding to Phase 3+.

### Probability of Profit
- Estimate using log-normal distribution of stock price
- P(stock > breakeven at expiry) = N(d2) from Black-Scholes
- Can also use a simple normal distribution approximation with IV-derived standard deviation

### Strategy Recommender Engine
- For a given target price and date:
  1. Calculate implied move = (target - current) / current
  2. Find the expiration date closest to target date
  3. Generate candidate strategies by iterating through strikes near the money
  4. For each candidate: compute payoff at target price, max profit, max loss, probability of profit
  5. Score and rank by a composite of: P(profit), risk/reward, and payoff at target price
  6. Return top 5

---

## Non-Functional Requirements

- **Performance:** Options chain should load within 2-3 seconds. Payoff calculations should be near-instant.
- **Error handling:** Graceful handling of invalid tickers, missing data, market-closed scenarios
- **Responsive:** Works well on a standard laptop screen (1440px wide). Mobile is not a priority.
- **No authentication needed** — this is a personal local tool

---

## Build Order (Suggested Phases for Claude Code)

### Phase 1: Foundation + Analysis Tab Core
- Set up React + Vite frontend with dark theme, top tab bar (Dashboard + Analysis)
- Set up Python/FastAPI backend with **DataProvider abstraction layer** (yfinance implementation)
- **Analysis Tab:** Ticker search → stock info context bar (Section 2A)
- **Analysis Tab:** Options chain viewer with expiry/strike filters (Section 2B)
- Tab navigation works but Dashboard tab shows placeholder content for now

### Phase 2: Strategy Builder + Payoff
- **Analysis Tab:** Click-to-add legs from chain (Section 2C)
- Strategy templates with auto-populated strikes
- Payoff diagram at expiration (Section 2D)
- Summary stats (max profit/loss, breakevens)

### Phase 3: Greeks + Stress Testing
- Implement Black-Scholes Greeks calculation
- **Run full Greeks stress test suite (see Greeks Stress Testing section) — ALL tests must pass**
- Add Greeks columns to options chain table
- Pre-expiration payoff curves with DTE time slider
- Probability of profit
- IV rank / IV percentile in context bar

### Phase 4: Dashboard Tab — Portfolio
- Portfolio data model and local JSON persistence
- Manual position entry form
- CSV upload and parsing
- Screenshot OCR ingestion (Robinhood format as primary target)
- Holdings table with real-time prices from yfinance
- Portfolio-level metrics (gross/net exposure, leverage ratio, P&L)
- Portfolio Greeks (aggregated delta, theta, vega, gamma, beta-weighted delta)
- Portfolio analytics (concentration chart, sector exposure, correlation flags)
- Click-through from holdings → Analysis tab with ticker pre-loaded

### Phase 5: Dashboard Tab — Watchlist, Market Overview, Alerts
- Market overview bar (SPY, QQQ, VIX, 10Y yield)
- Watchlist management (add/remove tickers, persistent storage)
- Watchlist table with IV rank, earnings dates
- Automated alerts engine (earnings, IV, expiration, large moves)
- Click-through from watchlist/alerts → Analysis tab

### Phase 6: Strategy Recommender
- **Analysis Tab:** Target price + date input (Section 2E)
- Strategy scanning engine
- Ranked recommendations with inline payoff charts
- "Load into builder" functionality

### Phase 7: Polish + Future-Proofing
- Strategy comparison view (Section 2F)
- UI refinements, animations, hover effects
- Error handling and edge cases
- Performance optimization
- Document how to swap in Schwab API via the DataProvider abstraction (README instructions for future migration)

---

## How to Run (for reference)

```bash
# Terminal 1: Start backend
cd backend
pip install -r requirements.txt
python main.py

# Terminal 2: Start frontend
cd frontend
npm install
npm run dev
```

Then open http://localhost:3000 in your browser.
