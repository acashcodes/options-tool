"""Newsletter configuration — all values from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class NewsletterConfig:
    enabled: bool = False
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"
    from_allowlist: List[str] = field(default_factory=list)
    use_idle: bool = True
    poll_seconds: int = 30
    db_path: str = "backend/data/newsletter.db"
    encryption_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_timeout: int = 20


def load_config() -> NewsletterConfig:
    """Load newsletter config from environment variables."""
    allowlist_raw = os.environ.get("NEWSLETTER_FROM_ALLOWLIST", "")
    allowlist = [e.strip() for e in allowlist_raw.split(",") if e.strip()]

    return NewsletterConfig(
        enabled=os.environ.get("NEWSLETTER_ENABLED", "false").lower() == "true",
        imap_host=os.environ.get("NEWSLETTER_IMAP_HOST", "imap.gmail.com"),
        imap_port=int(os.environ.get("NEWSLETTER_IMAP_PORT", "993")),
        imap_username=os.environ.get("NEWSLETTER_IMAP_USERNAME", ""),
        imap_password=os.environ.get("NEWSLETTER_IMAP_PASSWORD", ""),
        imap_folder=os.environ.get("NEWSLETTER_IMAP_FOLDER", "INBOX"),
        from_allowlist=allowlist,
        use_idle=os.environ.get("NEWSLETTER_USE_IDLE", "true").lower() == "true",
        poll_seconds=int(os.environ.get("NEWSLETTER_POLL_SECONDS", "30")),
        db_path=os.environ.get("NEWSLETTER_DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "newsletter.db")),
        encryption_key=os.environ.get("NEWSLETTER_ENCRYPTION_KEY", ""),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        openai_timeout=int(os.environ.get("OPENAI_TIMEOUT_SECONDS", "20")),
    )
