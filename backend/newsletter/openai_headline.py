"""OpenAI headline generation — one-line summary with no digits."""

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


def _strip_digits(text: str) -> str:
    """Remove any digits and % symbols from headline."""
    text = re.sub(r"[\d%]+", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _sanitize_fallback(subject: str) -> str:
    """Use subject as fallback, stripping digits."""
    return _strip_digits(subject) if subject else "Newsletter Update"
