"""Email parsing — extract structured data from raw MIME bytes."""

from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedEmail:
    message_id: str
    from_email: str
    subject: str
    received_at: str
    web_url: Optional[str]
    text_body: str
    html_body: str
    raw_mime: bytes


_WEB_URL_RE = re.compile(
    r"(?:View\s+(?:this\s+)?(?:post|email)\s+on\s+the\s+web\s+at|View\s+online[:\s]+)"
    r"\s*(https?://[^\s<>\"]+)",
    re.IGNORECASE,
)

_UNSUB_PATTERNS = [
    re.compile(r"(?:^|\n)[-_=]{3,}.*?unsubscribe.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"\nYou're receiving this.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"\nYou received this.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"\nTo stop receiving.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"\nClick here to unsubscribe.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"\n\[Unsubscribe\].*", re.IGNORECASE | re.DOTALL),
    re.compile(r"\nSent via Substack.*", re.IGNORECASE | re.DOTALL),
]


def parse_email(raw_bytes: bytes) -> ParsedEmail:
    """Parse raw MIME bytes into a structured ParsedEmail."""
    parser = BytesParser(policy=policy.default)
    msg = parser.parsebytes(raw_bytes)

    message_id = msg.get("Message-ID", "").strip("<>")
    from_header = msg.get("From", "")
    from_email = _extract_email(from_header)
    subject = msg.get("Subject", "")
    date_str = msg.get("Date", "")
    received_at = _parse_date(date_str)

    text_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not text_body:
                text_body = part.get_content() or ""
            elif ct == "text/html" and not html_body:
                html_body = part.get_content() or ""
    else:
        ct = msg.get_content_type()
        content = msg.get_content() or ""
        if ct == "text/plain":
            text_body = content
        elif ct == "text/html":
            html_body = content

    # If no plain text, convert HTML to text
    if not text_body and html_body:
        text_body = _html_to_text(html_body)

    # Normalize text
    text_body = _normalize_text(text_body)

    # Extract web URL (search HTML too for link extraction)
    web_url = None
    search_text = text_body or html_body
    m = _WEB_URL_RE.search(search_text)
    if m:
        web_url = m.group(1).rstrip(")")

    return ParsedEmail(
        message_id=message_id,
        from_email=from_email,
        subject=subject,
        received_at=received_at,
        web_url=web_url,
        text_body=text_body,
        html_body=html_body,
        raw_mime=raw_bytes,
    )


def _extract_email(from_header: str) -> str:
    """Extract bare email from 'Name <email>' format."""
    m = re.search(r"<([^>]+)>", from_header)
    return m.group(1) if m else from_header.strip()


def _parse_date(date_str: str) -> str:
    """Parse email date header to ISO8601."""
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


def _html_to_text(html: str) -> str:
    """Strip HTML tags to get plain text."""
    # Remove style and script blocks
    text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Convert <br>, <p>, <div>, <li> to newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    import html as html_mod
    text = html_mod.unescape(text)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_FWD_HEADER_RE = re.compile(
    r"^-{5,}\s*Forwarded message\s*-{5,}.*?\n\n",
    re.DOTALL | re.IGNORECASE,
)


def _normalize_text(text: str) -> str:
    """Normalize whitespace and strip unsubscribe footer."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip Gmail forwarding header
    text = _FWD_HEADER_RE.sub("", text)
    # Strip zero-width / invisible unicode junk (common in Substack emails)
    text = re.sub(r"[\u034f\u00ad\u2007\u200b\u200c\u200d\ufeff]+", "", text)
    # Strip any remaining HTML tags that leaked into text/plain
    if "<div" in text or "<br" in text or "<table" in text:
        text = _html_to_text(text)
    # Strip Substack/email boilerplate lines (tracking URLs, nav chrome)
    cleaned_lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Skip bare URL lines (tracking links, images)
        if stripped.startswith("<http") and stripped.endswith(">"):
            continue
        # Skip "Author Name <url>" byline lines
        if re.match(r"^.{1,40}\s+<https?://", stripped) and stripped.endswith(">"):
            continue
        # Skip Substack chrome lines
        if stripped in ("View in browser", "READ IN APP", "Paid", "Share"):
            continue
        if stripped == "\u2219" or stripped == "\u2022":  # lone bullet chars
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    for pattern in _UNSUB_PATTERNS:
        text = pattern.sub("", text)
    return text.strip()
