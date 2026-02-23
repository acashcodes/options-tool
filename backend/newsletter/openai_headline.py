"""OpenAI headline + summary generation — condensed industry-relevant takeaways."""

from __future__ import annotations

import re
import logging
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


def generate_headline(
    bullets: list[str],
    subject: str,
    api_key: str,
    model: str = "gpt-4o",
    timeout: int = 20,
) -> str:
    """Generate a single-line headline from extracted bullets using OpenAI.

    Rules:
    - One single line
    - No digits
    - No % symbols
    - No invented facts
    - Only reflect extracted bullets

    Falls back to subject line on any failure.
    """
    if not api_key or not bullets:
        return _sanitize_fallback(subject)

    bullet_text = "\n".join(f"- {b}" for b in bullets)
    prompt = (
        "Write exactly ONE headline sentence summarizing these newsletter highlights. "
        "Rules: no digits, no percent signs, no invented facts. "
        "Only reflect what the bullets say.\n\n"
        f"Bullets:\n{bullet_text}"
    )

    try:
        if OpenAI is None:
            return _sanitize_fallback(subject)

        client = OpenAI(api_key=api_key, timeout=timeout)
        response = client.responses.create(
            model=model,
            input=prompt,
        )
        headline = response.output_text.strip()
        # Validate: strip digits and % if the model disobeyed
        headline = _strip_digits(headline)
        return headline if headline else _sanitize_fallback(subject)
    except Exception as exc:
        logger.warning("OpenAI headline generation failed: %s", exc)
        return _sanitize_fallback(subject)


def generate_summary(
    full_text: str,
    portfolio_tickers: list[str],
    industries: list[str],
    api_key: str,
    model: str = "gpt-4o",
    timeout: int = 30,
) -> list[str]:
    """Generate a condensed 3-5 line summary of the full newsletter text.

    Instead of repeating bullet extracts from the email, this reads the entire
    newsletter and distills the big takeaways relevant to the portfolio's
    industries (tech, social, enterprise software, etc.).

    Returns a list of 3-5 summary lines. Falls back to empty list on failure.
    """
    if not api_key or not full_text or not full_text.strip():
        return []

    # Truncate very long newsletters to fit context
    truncated = full_text[:12000]

    tickers_str = ", ".join(portfolio_tickers[:15]) if portfolio_tickers else "general tech"
    industries_str = ", ".join(industries[:10]) if industries else "technology, software, social media"

    prompt = (
        "You are a concise financial analyst. Read the following newsletter and produce "
        "exactly 3 to 5 short summary lines (one sentence each). "
        "Focus on the big takeaways that are relevant to these industries: "
        f"{industries_str}. "
        f"Portfolio tickers for context: {tickers_str}. "
        "\n\nRules:\n"
        "- Each line should be a distinct insight or implication, not a repeat of the same point.\n"
        "- Focus on what it MEANS for these industries, not just what happened.\n"
        "- Be specific: mention company names or sectors when relevant.\n"
        "- Do NOT repeat raw sentences from the newsletter. Condense and synthesize.\n"
        "- Keep each line under 120 characters.\n"
        "- Output ONLY the summary lines, one per line, no numbering, no bullets.\n"
        f"\n---\nNEWSLETTER:\n{truncated}\n---"
    )

    try:
        if OpenAI is None:
            return []

        client = OpenAI(api_key=api_key, timeout=timeout)
        response = client.responses.create(
            model=model,
            input=prompt,
        )
        raw = response.output_text.strip()
        lines = [line.strip().lstrip("•-*123456789. ") for line in raw.split("\n") if line.strip()]
        # Keep 3-5 lines
        return lines[:5] if len(lines) >= 3 else lines
    except Exception as exc:
        logger.warning("OpenAI summary generation failed: %s", exc)
        return []


def _strip_digits(text: str) -> str:
    """Remove any digits and % symbols from headline."""
    text = re.sub(r"[\d%]+", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _sanitize_fallback(subject: str) -> str:
    """Use subject as fallback, stripping digits."""
    return _strip_digits(subject) if subject else "Newsletter Update"
