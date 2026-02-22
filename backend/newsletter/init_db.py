#!/usr/bin/env python3
"""Initialize the newsletter database.

Usage:
    python -m newsletter.init_db
    # or
    python backend/newsletter/init_db.py
"""

from __future__ import annotations

import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from newsletter.config import load_config
from newsletter.store import NewsletterStore


def main() -> None:
    config = load_config()
    db_path = config.db_path
    print(f"Initializing newsletter database at: {db_path}")
    store = NewsletterStore(db_path)
    store.init_db()
    print("Done. Table 'newsletter_issues' is ready.")


if __name__ == "__main__":
    main()
