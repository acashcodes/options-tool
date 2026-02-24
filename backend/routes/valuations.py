"""Valuations endpoints – fundamental data for summary table and comparison tool."""

from __future__ import annotations

import json
import math
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cache import TTLCache

logger = logging.getLogger(__name__)

# Caches per spec: financials 1h, estimates 1h, market cap 30s
_financials_cache = TTLCache(3600)
_estimates_cache = TTLCache(3600)
_mcap_cache = TTLCache(30)
_history_cache = TTLCache(300)

PEERS_PATH = Path(__file__).resolve().parent.parent / "data" / "peers.json"


class CompareRequest(BaseModel):
    symbols: list[str]


def _safe(val) -> float | None:
    """Return float or None. Never 0 for missing data."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return None


def _safe_div(num, den) -> float | None:
    """Safe division – returns None when denominator is None, 0, or negative (for P/E)."""
    if num is None or den is None:
        return None
    if den <= 0:
        return None
    return num / den


def _pct(val) -> float | None:
    if val is None:
        return None
    return round(val * 100, 2)


def _load_peers() -> dict[str, list[str]]:
    try:
        return json.loads(PEERS_PATH.read_text())
    except Exception:
        return {}


def _get_financials(symbol: str) -> dict[str, Any]:
    """Fetch quarterly income statement and balance sheet data."""
    cached = _financials_cache.get(symbol.upper())
    if cached is not None:
        return cached

    ticker = yf.Ticker(symbol)
    info = ticker.info
    result: dict[str, Any] = {"symbol": symbol.upper()}

    # --- Market cap (separate short cache) ---
    mcap = _mcap_cache.get(symbol.upper())
    if mcap is None:
        mcap = _safe(info.get("marketCap"))
        if mcap is not None:
            _mcap_cache.set(symbol.upper(), mcap)
    result["market_cap"] = mcap

    # --- Basic info ---
    result["name"] = info.get("shortName") or info.get("longName") or symbol.upper()
    result["sector"] = info.get("sector")
    result["industry"] = info.get("industry")
    shares = _safe(info.get("sharesOutstanding"))
    result["shares_outstanding"] = shares

    # --- TTM from quarterly financials ---
    try:
        q_income = ticker.quarterly_income_stmt
        if q_income is not None and not q_income.empty:
            # Revenue
            rev_row = None
            for label in ["Total Revenue", "Revenue"]:
                if label in q_income.index:
                    rev_row = q_income.loc[label]
                    break
            if rev_row is not None and len(rev_row) >= 4:
                vals = [_safe(v) for v in rev_row.iloc[:4]]
                if all(v is not None for v in vals):
                    result["ttm_revenue"] = sum(vals)
                elif _safe(info.get("totalRevenue")) is not None:
                    result["ttm_revenue"] = _safe(info.get("totalRevenue"))
                else:
                    result["ttm_revenue"] = None
            else:
                result["ttm_revenue"] = _safe(info.get("totalRevenue"))

            # Net Income
            ni_row = None
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in q_income.index:
                    ni_row = q_income.loc[label]
                    break
            if ni_row is not None and len(ni_row) >= 4:
                vals = [_safe(v) for v in ni_row.iloc[:4]]
                if all(v is not None for v in vals):
                    result["ttm_net_income"] = sum(vals)
                elif _safe(info.get("netIncomeToCommon")) is not None:
                    result["ttm_net_income"] = _safe(info.get("netIncomeToCommon"))
                else:
                    result["ttm_net_income"] = None
            else:
                result["ttm_net_income"] = _safe(info.get("netIncomeToCommon"))

            # Latest quarter
            if rev_row is not None and len(rev_row) >= 1:
                result["latest_q_revenue"] = _safe(rev_row.iloc[0])
            else:
                result["latest_q_revenue"] = None

            if ni_row is not None and len(ni_row) >= 1:
                result["latest_q_net_income"] = _safe(ni_row.iloc[0])
            else:
                result["latest_q_net_income"] = None
        else:
            result["ttm_revenue"] = _safe(info.get("totalRevenue"))
            result["ttm_net_income"] = _safe(info.get("netIncomeToCommon"))
            result["latest_q_revenue"] = None
            result["latest_q_net_income"] = None
    except Exception:
        result["ttm_revenue"] = _safe(info.get("totalRevenue"))
        result["ttm_net_income"] = _safe(info.get("netIncomeToCommon"))
        result["latest_q_revenue"] = None
        result["latest_q_net_income"] = None

    # --- EBITDA ---
    result["ebitda"] = _safe(info.get("ebitda"))

    # --- Gross / Operating margins ---
    result["gross_margin"] = _pct(info.get("grossMargins"))
    result["operating_margin"] = _pct(info.get("operatingMargins"))
    result["net_margin"] = _pct(info.get("profitMargins"))

    # --- Balance sheet: cash, debt, EV ---
    result["total_cash"] = _safe(info.get("totalCash"))
    result["total_debt"] = _safe(info.get("totalDebt"))
    cash = result["total_cash"] or 0
    debt = result["total_debt"] or 0
    result["net_cash"] = cash - debt if (result["total_cash"] is not None or result["total_debt"] is not None) else None
    result["enterprise_value"] = _safe(info.get("enterpriseValue"))

    # --- Free Cash Flow ---
    result["free_cash_flow"] = _safe(info.get("freeCashflow"))

    # --- P/S, P/E ---
    result["ps_ratio"] = _safe_div(mcap, result.get("ttm_revenue"))
    result["pe_ratio"] = _safe_div(mcap, result.get("ttm_net_income"))

    # --- EV multiples ---
    ev = result["enterprise_value"]
    result["ev_sales"] = _safe_div(ev, result.get("ttm_revenue"))
    result["ev_ebitda"] = _safe_div(ev, result.get("ebitda"))

    _financials_cache.set(symbol.upper(), result)
    return result


def _get_estimates(symbol: str, ttm_revenue: float | None = None) -> dict[str, Any]:
    """Fetch analyst estimates (forward revenue / EPS).

    ttm_revenue: pass TTM revenue from _get_financials to derive forward revenue
    from the YoY growth rate when direct estimates are unavailable.
    """
    cached = _estimates_cache.get(symbol.upper())
    if cached is not None:
        return cached

    ticker = yf.Ticker(symbol)
    info = ticker.info
    result: dict[str, Any] = {}

    # Revenue growth (YoY latest quarter) — needed for forward derivation
    rev_growth = info.get("revenueGrowth")  # decimal, e.g. 0.12 for 12%
    result["revenue_growth_yoy"] = _pct(rev_growth)

    # Forward revenue estimate — try direct first, then derive from growth rate
    result["forward_revenue"] = _safe(info.get("revenueEstimate")) or _safe(
        info.get("revenueEstimates", {}).get("avg") if isinstance(info.get("revenueEstimates"), dict) else None
    )

    # Derive forward revenue from TTM × (1 + growth) if not available directly
    if result["forward_revenue"] is None and ttm_revenue is not None and rev_growth is not None:
        try:
            growth_f = float(rev_growth)
            if not math.isnan(growth_f) and not math.isinf(growth_f):
                result["forward_revenue"] = ttm_revenue * (1 + growth_f)
        except (ValueError, TypeError):
            pass

    # Forward EPS → forward net income
    forward_eps = _safe(info.get("forwardEps"))
    shares = _safe(info.get("sharesOutstanding"))
    if forward_eps is not None and shares is not None:
        result["forward_net_income"] = forward_eps * shares
    else:
        result["forward_net_income"] = None

    result["forward_eps"] = forward_eps

    # Forward quarter estimates — derive from annual / 4
    fwd_rev = result.get("forward_revenue")
    fwd_ni = result.get("forward_net_income")
    result["forward_q_revenue"] = round(fwd_rev / 4, 2) if fwd_rev is not None else None
    result["forward_q_net_income"] = round(fwd_ni / 4, 2) if fwd_ni is not None else None

    _estimates_cache.set(symbol.upper(), result)
    return result


def _get_price_performance(symbol: str) -> dict[str, float | None]:
    """1M, 3M, 1Y price performance."""
    cached = _history_cache.get(f"perf:{symbol.upper()}")
    if cached is not None:
        return cached

    ticker = yf.Ticker(symbol)
    try:
        hist = ticker.history(period="1y")
        if hist.empty:
            return {"perf_1m": None, "perf_3m": None, "perf_1y": None}

        closes = hist["Close"]
        current = float(closes.iloc[-1])

        def _perf(n_days):
            if len(closes) < n_days:
                return None
            past = float(closes.iloc[-n_days])
            if past <= 0:
                return None
            return round(((current - past) / past) * 100, 2)

        result = {
            "perf_1m": _perf(21),
            "perf_3m": _perf(63),
            "perf_1y": _perf(min(252, len(closes))),
        }
    except Exception:
        result = {"perf_1m": None, "perf_3m": None, "perf_1y": None}

    _history_cache.set(f"perf:{symbol.upper()}", result)
    return result


def _build_company_data(symbol: str) -> dict[str, Any]:
    """Full company data: financials + estimates + performance."""
    fin = _get_financials(symbol)
    est = _get_estimates(symbol, ttm_revenue=fin.get("ttm_revenue"))
    perf = _get_price_performance(symbol)
    return {**fin, **est, **perf}


def create_valuations_routes(provider) -> APIRouter:
    router = APIRouter(prefix="/api/valuations", tags=["valuations"])

    @router.get("/summary")
    def get_summary(source: str = "all"):
        """Summary table data for portfolio + watchlist tickers."""
        from db import get_db

        tickers = set()

        if source in ("all", "portfolio"):
            with get_db() as conn:
                rows = conn.execute("SELECT DISTINCT ticker FROM positions").fetchall()
                for r in rows:
                    tickers.add(r[0].upper())

        if source in ("all", "watchlist"):
            with get_db() as conn:
                rows = conn.execute("SELECT ticker FROM watchlist").fetchall()
                for r in rows:
                    tickers.add(r[0].upper())

        if not tickers:
            return {"tickers": []}

        results = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(_build_company_data, t): t for t in tickers}
            for future in as_completed(futures):
                try:
                    data = future.result()
                    results.append(data)
                except Exception as exc:
                    t = futures[future]
                    logger.warning("Failed to fetch valuations for %s: %s", t, exc)

        results.sort(key=lambda x: (x.get("market_cap") or 0), reverse=True)
        return {"tickers": results}

    @router.get("/company/{symbol}")
    def get_company(symbol: str):
        """Full valuation data for a single company."""
        try:
            return _build_company_data(symbol.upper())
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.get("/peers/{symbol}")
    def get_peers(symbol: str):
        """Peers for a given symbol: explicit peers.json, then industry/sector fallback."""
        sym = symbol.upper()
        peers_map = _load_peers()

        # Explicit peers
        peer_list = peers_map.get(sym)

        if not peer_list:
            # Fallback: same industry/sector from portfolio + watchlist
            try:
                primary = _get_financials(sym)
            except Exception:
                return {"symbol": sym, "peers": []}

            industry = primary.get("industry")
            sector = primary.get("sector")

            if not industry and not sector:
                return {"symbol": sym, "peers": []}

            # Gather all known tickers
            from db import get_db
            all_tickers = set()
            with get_db() as conn:
                for r in conn.execute("SELECT DISTINCT ticker FROM positions").fetchall():
                    all_tickers.add(r[0].upper())
                for r in conn.execute("SELECT ticker FROM watchlist").fetchall():
                    all_tickers.add(r[0].upper())
            all_tickers.discard(sym)

            # Try industry first, then sector
            industry_matches = []
            sector_matches = []
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = {pool.submit(_get_financials, t): t for t in all_tickers}
                for future in as_completed(futures):
                    try:
                        data = future.result()
                        if industry and data.get("industry") == industry:
                            industry_matches.append(data["symbol"])
                        elif sector and data.get("sector") == sector:
                            sector_matches.append(data["symbol"])
                    except Exception:
                        pass

            peer_list = industry_matches[:5] if len(industry_matches) >= 2 else (industry_matches + sector_matches)[:5]

        if not peer_list:
            return {"symbol": sym, "peers": []}

        # Fetch valuation data for peers
        results = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(_build_company_data, p): p for p in peer_list[:5]}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception:
                    pass

        results.sort(key=lambda x: (x.get("market_cap") or 0), reverse=True)
        return {"symbol": sym, "peers": results}

    @router.post("/compare")
    def compare(req: CompareRequest):
        """Side-by-side comparison for up to 3 tickers."""
        symbols = [s.upper() for s in req.symbols[:3]]
        results = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(_build_company_data, s): s for s in symbols}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    s = futures[future]
                    logger.warning("Compare failed for %s: %s", s, exc)

        # Maintain requested order
        order = {s: i for i, s in enumerate(symbols)}
        results.sort(key=lambda x: order.get(x.get("symbol", ""), 99))
        return {"companies": results}

    return router
