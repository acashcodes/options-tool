"""Relevance extraction — deterministic bullet extraction from newsletter text."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RelevanceResult:
    context_bullets: list[str]
    portfolio_bullets: list[str]
    watchlist_bullets: list[str]


MAX_BULLETS_PER_SECTION = 8


def extract_relevance(
    text: str,
    portfolio_tickers: list[str],
    watchlist_tickers: list[str],
) -> RelevanceResult:
    """Extract bullets from newsletter text based on ticker relevance.

    Rules:
    - context_bullets: 2-3 lines from the preamble (opening paragraph)
    - portfolio_bullets: lines mentioning portfolio tickers (exact word-boundary match)
    - watchlist_bullets: lines mentioning watchlist-only tickers
    - Extractive only — no paraphrasing
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Context bullets: first 2-3 substantive lines (skip very short lines)
    context_bullets = []
    for line in lines:
        if len(line) > 30:
            context_bullets.append(line)
            if len(context_bullets) >= 3:
                break

    # Build ticker regexes
    portfolio_set = {t.upper() for t in portfolio_tickers}
    watchlist_set = {t.upper() for t in watchlist_tickers} - portfolio_set

    portfolio_bullets = []
    watchlist_bullets = []

    for line in lines:
        if len(line) < 10:
            continue
        upper_line = line.upper()

        # Check portfolio tickers
        for ticker in portfolio_set:
            if _ticker_in_text(ticker, upper_line):
                if line not in portfolio_bullets:
                    portfolio_bullets.append(line)
                break

        # Check watchlist-only tickers
        for ticker in watchlist_set:
            if _ticker_in_text(ticker, upper_line):
                if line not in watchlist_bullets and line not in portfolio_bullets:
                    watchlist_bullets.append(line)
                break

    return RelevanceResult(
        context_bullets=context_bullets[:3],
        portfolio_bullets=portfolio_bullets[:MAX_BULLETS_PER_SECTION],
        watchlist_bullets=watchlist_bullets[:MAX_BULLETS_PER_SECTION],
    )


def _ticker_in_text(ticker: str, text_upper: str) -> bool:
    """Exact word-boundary match for a ticker symbol."""
    pattern = r"\b" + re.escape(ticker) + r"\b"
    return bool(re.search(pattern, text_upper))
