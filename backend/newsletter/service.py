"""Newsletter service — orchestrates parsing, relevance, headline, and storage."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from .config import NewsletterConfig
from .crypto import EmailCrypto
from .parser import parse_email
from .relevance import extract_relevance
from .openai_headline import generate_headline, generate_summary
from .store import NewsletterStore

logger = logging.getLogger(__name__)

# Known Substack author mappings: email local part -> display name
_KNOWN_AUTHORS = {
    "tmtbreakout": "TMTBreakout",
    "sleepysol": "SleepySol",
}


class NewsletterService:
    """Main service that processes raw emails end-to-end."""

    def __init__(self, config: NewsletterConfig) -> None:
        self.config = config
        self.store = NewsletterStore(config.db_path)
        self.crypto = EmailCrypto(config.encryption_key) if config.encryption_key else None
        self.store.init_db()

    def process_raw_email(
        self,
        raw_bytes: bytes,
        portfolio_tickers: list[str],
        watchlist_tickers: list[str],
        portfolio_industries: list[str] | None = None,
    ) -> Optional[dict]:
        """Process a raw MIME email: parse, extract, headline, summarize, encrypt, store.

        Returns the stored issue dict or None if skipped (duplicate).
        """
        parsed = parse_email(raw_bytes)

        # Skip duplicates
        if parsed.message_id and self.store.message_id_exists(parsed.message_id):
            logger.info("Skipping duplicate message_id: %s", parsed.message_id)
            return None

        # Extract relevance — prefer cleaned text, fall back to HTML→text conversion
        body = parsed.text_body
        if not body or len(body.strip()) < 50:
            # text/plain was empty or too short; convert HTML
            if parsed.html_body:
                from .parser import _html_to_text, _normalize_text
                body = _normalize_text(_html_to_text(parsed.html_body))
        if not body:
            body = parsed.html_body  # last resort
        logger.info(
            "Processing %s: text_body=%d chars, html_body=%d chars, using_body=%d chars",
            parsed.subject[:50], len(parsed.text_body), len(parsed.html_body), len(body),
        )
        relevance = extract_relevance(body, portfolio_tickers, watchlist_tickers)

        # Generate headline
        all_bullets = (
            relevance.context_bullets
            + relevance.portfolio_bullets
            + relevance.watchlist_bullets
        )
        headline = generate_headline(
            all_bullets,
            parsed.subject,
            self.config.openai_api_key,
            self.config.openai_model,
            self.config.openai_timeout,
        )

        # Generate condensed summary (3-5 lines of industry-relevant takeaways)
        industries = portfolio_industries or ["technology", "software", "social media"]
        summary_lines = generate_summary(
            body,
            portfolio_tickers,
            industries,
            self.config.openai_api_key,
            self.config.openai_model,
            self.config.openai_timeout,
        )

        # Derive source name — detect actual author from forwarded emails
        source_name = _derive_source_name(parsed.from_email, body)

        # Encrypt raw content
        raw_mime_enc = self.crypto.encrypt(parsed.raw_mime) if self.crypto else None
        raw_text_enc = self.crypto.encrypt(parsed.text_body) if self.crypto and parsed.text_body else None
        raw_html_enc = self.crypto.encrypt(parsed.html_body) if self.crypto and parsed.html_body else None

        issue = {
            "id": str(uuid.uuid4()),
            "source_name": source_name,
            "from_email": parsed.from_email,
            "subject": parsed.subject,
            "received_at": parsed.received_at,
            "message_id": parsed.message_id,
            "web_url": parsed.web_url,
            "raw_mime_enc": raw_mime_enc,
            "raw_text_enc": raw_text_enc,
            "raw_html_enc": raw_html_enc,
            "headline": headline,
            "context_bullets": relevance.context_bullets,
            "portfolio_bullets": relevance.portfolio_bullets,
            "watchlist_bullets": relevance.watchlist_bullets,
            "summary_lines": summary_lines,
        }

        self.store.insert_issue(issue)
        logger.info("Stored newsletter issue %s: %s", issue["id"], headline)
        return issue

    def get_latest(self) -> Optional[dict]:
        return self.store.get_latest()

    def get_issue(self, issue_id: str) -> Optional[dict]:
        return self.store.get_issue(issue_id, include_encrypted=False)

    def get_issue_full(self, issue_id: str) -> Optional[dict]:
        """Get issue including decrypted raw content."""
        issue = self.store.get_issue(issue_id, include_encrypted=True)
        if not issue:
            return None
        # Decrypt raw content if available
        if self.crypto:
            if issue.get("raw_text_enc"):
                issue["raw_text"] = self.crypto.decrypt_text(issue["raw_text_enc"])
            if issue.get("raw_html_enc"):
                issue["raw_html"] = self.crypto.decrypt_text(issue["raw_html_enc"])
        # Remove encrypted blobs from response
        issue.pop("raw_mime_enc", None)
        issue.pop("raw_text_enc", None)
        issue.pop("raw_html_enc", None)
        return issue

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.store.get_history(limit, offset)

    def mark_read(self, issue_id: str) -> bool:
        return self.store.mark_read(issue_id)

    def delete_issue(self, issue_id: str) -> bool:
        return self.store.delete_issue(issue_id)


def _derive_source_name(from_email: str, body: str = "") -> str:
    """Derive the actual newsletter author name.

    For forwarded emails, the From header may be the forwarder, not the author.
    This function checks:
    1. Known author mappings from email local part
    2. Substack URL patterns in the body to detect the real author
    3. Fallback: title-case the email local part
    """
    local = from_email.split("@")[0].lower() if "@" in from_email else from_email.lower()
    domain = from_email.split("@")[1].lower() if "@" in from_email else ""

    # Direct match from known authors
    if local in _KNOWN_AUTHORS:
        return _KNOWN_AUTHORS[local]

    # Check for Substack domain — extract from email directly
    if "substack.com" in domain:
        return _KNOWN_AUTHORS.get(local, _format_author_name(local))

    # For forwarded emails, try to detect original author from body content
    # Look for Substack URL patterns like "tmtbreakout.substack.com"
    substack_match = re.search(r"(\w+)\.substack\.com", body or "")
    if substack_match:
        author_slug = substack_match.group(1).lower()
        if author_slug in _KNOWN_AUTHORS:
            return _KNOWN_AUTHORS[author_slug]
        return _format_author_name(author_slug)

    # Look for "by AuthorName" or "from AuthorName" patterns common in forwarded newsletters
    by_match = re.search(r"(?:^|\n)\s*(?:by|from|written by)\s+([A-Z][\w\s]{2,30}?)(?:\s*[|\n\r])", body or "", re.IGNORECASE)
    if by_match:
        candidate = by_match.group(1).strip()
        # Only use if it looks like a name (not a generic phrase)
        if len(candidate.split()) <= 3 and not any(w in candidate.lower() for w in ["the", "this", "your", "our"]):
            return candidate

    # Fallback: format from email local part
    return _format_author_name(local)


def _format_author_name(local: str) -> str:
    """Format an email local part into a display name."""
    parts = local.replace("_", " ").replace("-", " ").replace(".", " ").split()
    return " ".join(p.capitalize() for p in parts) if parts else local
