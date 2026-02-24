"""Dashboard routes: market overview, watchlist, alerts, news."""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any, Optional, TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_provider import DataProvider
import watchlist_store as wl_store
import portfolio_store as port_store
import alerts_store

if TYPE_CHECKING:
    from newsletter.service import NewsletterService

logger = logging.getLogger(__name__)

# Simple in-memory cache for grouped news (5 min TTL)
_grouped_news_cache: dict[str, Any] = {"data": None, "ts": 0}


class WatchlistAdd(BaseModel):
    ticker: str


class AlertDismiss(BaseModel):
    alert_id: str


class ThresholdsUpdate(BaseModel):
    earnings_days: Optional[int] = None
    iv_high: Optional[float] = None
    iv_low: Optional[float] = None
    large_move_pct: Optional[float] = None
    expiration_days: Optional[int] = None


def create_dashboard_routes(provider: DataProvider, newsletter_service: Optional["NewsletterService"] = None) -> APIRouter:
    router = APIRouter(prefix="/api/dashboard")

    # ---- Market Overview ----

    @router.get("/overview")
    def market_overview():
        """Fetch SPY, QQQ, VIX, TNX in parallel. Returns lightweight quote data."""
        symbols = {
            "spy": "SPY",
            "qqq": "QQQ",
            "vix": "^VIX",
            "tnx": "^TNX",
        }
        results = {}

        def fetch_one(key: str, symbol: str) -> tuple[str, dict]:
            try:
                q = provider.get_quote_light(symbol)
                result = {
                    "symbol": q.get("symbol", symbol),
                    "price": q.get("price"),
                    "change": q.get("change"),
                    "change_percent": q.get("change_percent"),
                }
                # Fix ^TNX scaling: index is 10x the yield
                if key == "tnx" and result["price"] is not None:
                    from assumptions import tnx_to_yield_percent
                    raw_price = result["price"]
                    raw_change = result["change"]
                    result["price"] = tnx_to_yield_percent(raw_price)
                    if raw_change is not None:
                        result["change"] = raw_change / 10.0
                        prev_yield = result["price"] - result["change"]
                        result["change_percent"] = (result["change"] / prev_yield * 100) if prev_yield else None
                return key, result
            except Exception:
                return key, {
                    "symbol": symbol,
                    "price": None,
                    "change": None,
                    "change_percent": None,
                }

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fetch_one, k, s): k for k, s in symbols.items()}
            for fut in as_completed(futures):
                key, data = fut.result()
                results[key] = data

        return results

    # ---- Watchlist CRUD ----

    @router.get("/watchlist")
    def get_watchlist():
        return {"tickers": wl_store.load_watchlist()}

    @router.post("/watchlist")
    def add_to_watchlist(req: WatchlistAdd):
        t = req.ticker.strip().upper()
        if not t:
            raise HTTPException(status_code=400, detail="Ticker is required")
        tickers = wl_store.add_ticker(t)
        return {"tickers": tickers}

    @router.delete("/watchlist/{ticker}")
    def remove_from_watchlist(ticker: str):
        tickers = wl_store.remove_ticker(ticker)
        return {"tickers": tickers}

    # ---- Watchlist Enriched ----

    @router.get("/watchlist/enriched")
    def get_enriched_watchlist():
        """Fetch live data for all watchlist tickers in parallel."""
        tickers = wl_store.load_watchlist()
        if not tickers:
            return {"items": []}

        enriched: list[dict[str, Any]] = []

        def fetch_quote(symbol: str) -> dict[str, Any]:
            try:
                q = provider.get_quote(symbol)
                return {
                    "ticker": q.get("symbol", symbol),
                    "name": q.get("name"),
                    "price": q.get("price"),
                    "change": q.get("change"),
                    "change_percent": q.get("change_percent"),
                    "iv_rank": q.get("iv_rank"),
                    "iv_percentile": q.get("iv_percentile"),
                    "high_52w": q.get("high_52w"),
                    "low_52w": q.get("low_52w"),
                    "earnings_date": q.get("earnings_date"),
                }
            except Exception:
                return {"ticker": symbol, "price": None, "error": True}

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(fetch_quote, t): t for t in tickers}
            for fut in as_completed(futures):
                enriched.append(fut.result())

        # Preserve watchlist order
        order = {t: i for i, t in enumerate(tickers)}
        enriched.sort(key=lambda x: order.get(x.get("ticker", ""), 999))

        return {"items": enriched}

    # ---- Alerts ----

    @router.get("/alerts")
    def get_alerts():
        """Generate alerts from portfolio + watchlist data, grouped by ticker."""
        today = date.today()
        thresholds = alerts_store.get_thresholds()
        dismissed = set(alerts_store.get_dismissed())

        # Gather all tickers
        positions = port_store.load_positions()
        watchlist_tickers = wl_store.load_watchlist()
        portfolio_tickers = list({p.ticker.upper() for p in positions})
        all_tickers = list(set(portfolio_tickers + watchlist_tickers))

        if not all_tickers:
            return {"alerts": [], "groups": [], "dismissed_count": len(dismissed),
                    "thresholds": thresholds}

        # Fetch full quotes in parallel
        quotes: dict[str, dict] = {}

        def fetch_q(symbol: str) -> tuple[str, dict]:
            try:
                return symbol, provider.get_quote(symbol)
            except Exception:
                return symbol, {}

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(fetch_q, t) for t in all_tickers]
            for fut in as_completed(futures):
                sym, q = fut.result()
                quotes[sym] = q

        all_alerts: list[dict[str, Any]] = []

        # --- Earnings alerts ---
        earn_days = thresholds.get("earnings_days", 7)
        for ticker, q in quotes.items():
            ed = q.get("earnings_date")
            if ed:
                try:
                    ed_date = datetime.strptime(str(ed), "%Y-%m-%d").date()
                    days_until = (ed_date - today).days
                    if 0 <= days_until <= earn_days:
                        all_alerts.append({
                            "id": f"earnings-{ticker}",
                            "type": "earnings",
                            "ticker": ticker,
                            "message": f"{ticker} earnings in {days_until} day{'s' if days_until != 1 else ''}",
                            "severity": "warning",
                        })
                except ValueError:
                    pass

        # --- IV alerts ---
        iv_hi = thresholds.get("iv_high", 80)
        iv_lo = thresholds.get("iv_low", 20)
        for ticker, q in quotes.items():
            iv_rank = q.get("iv_rank")
            if iv_rank is not None:
                if iv_rank > iv_hi:
                    all_alerts.append({
                        "id": f"iv_high-{ticker}",
                        "type": "iv_high",
                        "ticker": ticker,
                        "message": f"{ticker} IV rank at {iv_rank:.0f}% \u2014 elevated",
                        "severity": "info",
                    })
                elif iv_rank < iv_lo:
                    all_alerts.append({
                        "id": f"iv_low-{ticker}",
                        "type": "iv_low",
                        "ticker": ticker,
                        "message": f"{ticker} IV rank at {iv_rank:.0f}% \u2014 depressed",
                        "severity": "info",
                    })

        # --- Option expiration alerts ---
        exp_days = thresholds.get("expiration_days", 7)
        for pos in positions:
            if pos.expiration and pos.asset_type in ("call", "put"):
                try:
                    exp_date = datetime.strptime(pos.expiration, "%Y-%m-%d").date()
                    days_left = (exp_date - today).days
                    if 0 <= days_left <= exp_days:
                        aid = f"expiry-{pos.ticker}-{pos.strike}-{pos.expiration}"
                        all_alerts.append({
                            "id": aid,
                            "type": "expiration",
                            "ticker": pos.ticker.upper(),
                            "message": f"Your {pos.ticker.upper()} ${pos.strike} {pos.asset_type} expires in {days_left} day{'s' if days_left != 1 else ''}",
                            "severity": "danger",
                        })
                except ValueError:
                    pass

        # --- Large move alerts ---
        move_pct = thresholds.get("large_move_pct", 3)
        for ticker, q in quotes.items():
            cp = q.get("change_percent")
            if cp is not None and abs(cp) > move_pct:
                direction = "up" if cp > 0 else "down"
                all_alerts.append({
                    "id": f"move-{ticker}",
                    "type": "large_move",
                    "ticker": ticker,
                    "message": f"{ticker} moved {abs(cp):.1f}% {direction} today",
                    "severity": "warning" if abs(cp) > 5 else "info",
                })

        # Mark dismissed
        for a in all_alerts:
            a["dismissed"] = a["id"] in dismissed

        # Sort: danger first, then warning, then info
        severity_order = {"danger": 0, "warning": 1, "info": 2}
        all_alerts.sort(key=lambda a: (
            1 if a["dismissed"] else 0,
            severity_order.get(a["severity"], 99),
        ))

        # Group by ticker
        groups: dict[str, list] = defaultdict(list)
        for a in all_alerts:
            groups[a["ticker"]].append(a)

        grouped = [
            {"ticker": ticker, "alerts": alerts_list}
            for ticker, alerts_list in groups.items()
        ]
        # Sort groups: tickers with danger alerts first
        def group_priority(g):
            severities = [severity_order.get(a["severity"], 99) for a in g["alerts"] if not a["dismissed"]]
            return min(severities) if severities else 99
        grouped.sort(key=group_priority)

        active_count = sum(1 for a in all_alerts if not a["dismissed"])

        # Include newsletter data if available
        newsletter = None
        if newsletter_service:
            try:
                newsletter = newsletter_service.get_latest()
            except Exception:
                pass

        return {
            "alerts": all_alerts,
            "groups": grouped,
            "active_count": active_count,
            "dismissed_count": len(dismissed),
            "thresholds": thresholds,
            "newsletter": newsletter,
        }

    @router.post("/alerts/dismiss")
    def dismiss_alert(req: AlertDismiss):
        dismissed = alerts_store.dismiss_alert(req.alert_id)
        return {"dismissed": dismissed}

    @router.post("/alerts/restore")
    def restore_alert(req: AlertDismiss):
        dismissed = alerts_store.restore_alert(req.alert_id)
        return {"dismissed": dismissed}

    @router.delete("/alerts/dismissed")
    def clear_dismissed():
        alerts_store.clear_dismissed()
        return {"dismissed": []}

    @router.get("/alerts/thresholds")
    def get_thresholds():
        return alerts_store.get_thresholds()

    @router.put("/alerts/thresholds")
    def update_thresholds(req: ThresholdsUpdate):
        updates = {k: v for k, v in req.model_dump().items() if v is not None}
        thresholds = alerts_store.set_thresholds(updates)
        return thresholds

    # ---- News ----

    _BLOCKED_PUBLISHERS = {
        "motley fool", "the motley fool",
        "investor's business daily", "investors.com",
        "stockstory", "stock story",
        "investorplace", "investor place",
        "insidermonkey", "insider monkey",
        "24/7 wall st", "247wallst",
        "benzinga",
        "seeking alpha",
        "tipranks",
        "zacks", "zacks investment research",
    }

    @router.get("/news")
    def get_news():
        """Fetch recent news for portfolio + watchlist tickers via yfinance."""
        positions = port_store.load_positions()
        watchlist_tickers = wl_store.load_watchlist()
        portfolio_tickers = list({p.ticker.upper() for p in positions})
        all_tickers = list(set(portfolio_tickers + watchlist_tickers))

        if not all_tickers:
            return {"articles": []}

        articles: list[dict[str, Any]] = []

        def fetch_news(symbol: str) -> list[dict[str, Any]]:
            try:
                import yfinance as yf
                t = yf.Ticker(symbol)
                news = t.news or []
                result = []
                for item in news[:5]:
                    content = item.get("content", {})
                    if not content:
                        continue
                    publisher = content.get("provider", {}).get("displayName", "")
                    # Skip blocked publishers (substring match)
                    pub_lower = publisher.lower().strip()
                    if any(blocked in pub_lower for blocked in _BLOCKED_PUBLISHERS):
                        continue
                    pub = content.get("pubDate", "")
                    result.append({
                        "ticker": symbol,
                        "title": content.get("title", ""),
                        "publisher": publisher,
                        "link": content.get("canonicalUrl", {}).get("url", ""),
                        "published": pub,
                        "type": content.get("contentType", ""),
                    })
                return result
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(fetch_news, t) for t in all_tickers[:10]]
            for fut in as_completed(futures):
                articles.extend(fut.result())

        # Sort by published date (newest first), deduplicate by title
        seen_titles = set()
        unique = []
        for a in articles:
            if a["title"] and a["title"] not in seen_titles:
                seen_titles.add(a["title"])
                unique.append(a)

        unique.sort(key=lambda a: a.get("published", ""), reverse=True)
        return {"articles": unique[:20]}

    # ---- Grouped News (AI-powered condensation) ----

    def _condense_articles_openai(ticker: str, articles: list[dict]) -> dict | None:
        """Use OpenAI to condense multiple articles about the same ticker."""
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None

        try:
            from openai import OpenAI
        except ImportError:
            return None

        titles = "\n".join(f"- {a['title']}" for a in articles if a.get("title"))
        if not titles:
            return None

        prompt = (
            f"Condense these {len(articles)} news articles about {ticker} into 2-3 sentences. "
            "Focus on: (1) what happened, (2) why it matters, (3) implications for the stock. "
            "Be specific and actionable. No filler phrases.\n\n"
            f"Articles:\n{titles}"
        )

        try:
            client = OpenAI(api_key=api_key, timeout=20)
            model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            response = client.responses.create(model=model, input=prompt)
            summary = response.output_text.strip()
            return summary if summary else None
        except Exception as exc:
            logger.warning("OpenAI news condensation failed for %s: %s", ticker, exc)
            return None

    @router.get("/news/grouped")
    def get_news_grouped():
        """Fetch news, group by ticker, and condense with AI summaries."""
        global _grouped_news_cache

        # Return cached data if fresh (5 min TTL)
        now = time.time()
        if _grouped_news_cache["data"] is not None and (now - _grouped_news_cache["ts"]) < 300:
            return _grouped_news_cache["data"]

        # 1. Fetch flat news (reuse existing logic)
        positions = port_store.load_positions()
        watchlist_tickers = wl_store.load_watchlist()
        portfolio_tickers = list({p.ticker.upper() for p in positions})
        all_tickers = list(set(portfolio_tickers + watchlist_tickers))

        if not all_tickers:
            result = {"groups": [], "ungrouped": []}
            _grouped_news_cache = {"data": result, "ts": now}
            return result

        articles: list[dict[str, Any]] = []

        def fetch_news(symbol: str) -> list[dict[str, Any]]:
            try:
                import yfinance as yf
                t = yf.Ticker(symbol)
                news = t.news or []
                result = []
                for item in news[:5]:
                    content = item.get("content", {})
                    if not content:
                        continue
                    publisher = content.get("provider", {}).get("displayName", "")
                    pub_lower = publisher.lower().strip()
                    if any(blocked in pub_lower for blocked in _BLOCKED_PUBLISHERS):
                        continue
                    pub = content.get("pubDate", "")
                    result.append({
                        "ticker": symbol,
                        "title": content.get("title", ""),
                        "publisher": publisher,
                        "link": content.get("canonicalUrl", {}).get("url", ""),
                        "published": pub,
                        "type": content.get("contentType", ""),
                    })
                return result
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(fetch_news, t) for t in all_tickers[:10]]
            for fut in as_completed(futures):
                articles.extend(fut.result())

        # Deduplicate by title
        seen_titles: set[str] = set()
        unique: list[dict] = []
        for a in articles:
            if a["title"] and a["title"] not in seen_titles:
                seen_titles.add(a["title"])
                unique.append(a)
        unique.sort(key=lambda a: a.get("published", ""), reverse=True)

        # 2. Group by ticker
        by_ticker: dict[str, list[dict]] = defaultdict(list)
        for a in unique:
            by_ticker[a["ticker"]].append(a)

        # 3. For tickers with 2+ articles, condense with AI
        groups: list[dict] = []
        ungrouped: list[dict] = []

        # Run AI condensation in parallel for eligible groups
        ticker_groups = {t: arts for t, arts in by_ticker.items() if len(arts) >= 2}
        single_articles = [arts[0] for t, arts in by_ticker.items() if len(arts) == 1]

        ai_results: dict[str, str | None] = {}
        if ticker_groups:
            def condense_one(ticker: str, arts: list[dict]) -> tuple[str, str | None]:
                return ticker, _condense_articles_openai(ticker, arts)

            with ThreadPoolExecutor(max_workers=4) as executor:
                futs = {
                    executor.submit(condense_one, t, arts): t
                    for t, arts in ticker_groups.items()
                }
                for fut in as_completed(futs):
                    t, summary = fut.result()
                    ai_results[t] = summary

        for ticker, arts in ticker_groups.items():
            summary = ai_results.get(ticker)
            groups.append({
                "ticker": ticker,
                "summary": summary,  # None if AI unavailable — frontend shows fallback
                "count": len(arts),
                "articles": arts,
            })

        # Sort groups: most articles first
        groups.sort(key=lambda g: g["count"], reverse=True)

        # Ungrouped = single-article tickers
        ungrouped = single_articles
        ungrouped.sort(key=lambda a: a.get("published", ""), reverse=True)

        result = {"groups": groups, "ungrouped": ungrouped}
        _grouped_news_cache = {"data": result, "ts": now}
        return result

    return router
