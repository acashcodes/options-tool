"""Newsletter SQLite store — encrypted storage for newsletter issues."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional


class NewsletterStore:
    """CRUD for the newsletter_issues table."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def _db(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create the newsletter_issues table if it doesn't exist."""
        with self._db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS newsletter_issues (
                    id TEXT PRIMARY KEY,
                    source_name TEXT,
                    from_email TEXT,
                    subject TEXT,
                    received_at TEXT,
                    message_id TEXT UNIQUE,
                    web_url TEXT,
                    raw_mime_enc BLOB,
                    raw_text_enc BLOB,
                    raw_html_enc BLOB,
                    headline TEXT,
                    context_bullets_json TEXT,
                    portfolio_bullets_json TEXT,
                    watchlist_bullets_json TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    read INTEGER DEFAULT 0
                )
            """)

    def message_id_exists(self, message_id: str) -> bool:
        with self._db() as conn:
            row = conn.execute(
                "SELECT 1 FROM newsletter_issues WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            return row is not None

    def insert_issue(self, issue: dict[str, Any]) -> None:
        with self._db() as conn:
            conn.execute(
                """INSERT INTO newsletter_issues
                   (id, source_name, from_email, subject, received_at,
                    message_id, web_url, raw_mime_enc, raw_text_enc, raw_html_enc,
                    headline, context_bullets_json, portfolio_bullets_json,
                    watchlist_bullets_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    issue["id"],
                    issue.get("source_name"),
                    issue.get("from_email"),
                    issue.get("subject"),
                    issue.get("received_at"),
                    issue.get("message_id"),
                    issue.get("web_url"),
                    issue.get("raw_mime_enc"),
                    issue.get("raw_text_enc"),
                    issue.get("raw_html_enc"),
                    issue.get("headline"),
                    json.dumps(issue.get("context_bullets", [])),
                    json.dumps(issue.get("portfolio_bullets", [])),
                    json.dumps(issue.get("watchlist_bullets", [])),
                ),
            )

    def get_latest(self) -> Optional[dict[str, Any]]:
        with self._db() as conn:
            row = conn.execute(
                """SELECT id, source_name, from_email, subject, received_at,
                          message_id, web_url, headline,
                          context_bullets_json, portfolio_bullets_json,
                          watchlist_bullets_json, created_at, read
                   FROM newsletter_issues
                   ORDER BY received_at DESC LIMIT 1"""
            ).fetchone()
            return self._row_to_summary(row) if row else None

    def get_issue(self, issue_id: str, include_encrypted: bool = False) -> Optional[dict[str, Any]]:
        cols = """id, source_name, from_email, subject, received_at,
                  message_id, web_url, headline,
                  context_bullets_json, portfolio_bullets_json,
                  watchlist_bullets_json, created_at, read"""
        if include_encrypted:
            cols += ", raw_mime_enc, raw_text_enc, raw_html_enc"
        with self._db() as conn:
            row = conn.execute(
                f"SELECT {cols} FROM newsletter_issues WHERE id = ?",
                (issue_id,),
            ).fetchone()
            if not row:
                return None
            result = self._row_to_summary(row)
            if include_encrypted:
                result["raw_mime_enc"] = row["raw_mime_enc"]
                result["raw_text_enc"] = row["raw_text_enc"]
                result["raw_html_enc"] = row["raw_html_enc"]
            return result

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._db() as conn:
            rows = conn.execute(
                """SELECT id, source_name, from_email, subject, received_at,
                          headline, created_at, read
                   FROM newsletter_issues
                   ORDER BY received_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "source_name": r["source_name"],
                    "from_email": r["from_email"],
                    "subject": r["subject"],
                    "received_at": r["received_at"],
                    "headline": r["headline"],
                    "created_at": r["created_at"],
                    "read": bool(r["read"]),
                }
                for r in rows
            ]

    def mark_read(self, issue_id: str) -> bool:
        with self._db() as conn:
            cur = conn.execute(
                "UPDATE newsletter_issues SET read = 1 WHERE id = ?",
                (issue_id,),
            )
            return cur.rowcount > 0

    def _row_to_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "source_name": row["source_name"],
            "from_email": row["from_email"],
            "subject": row["subject"],
            "received_at": row["received_at"],
            "message_id": row["message_id"],
            "web_url": row["web_url"],
            "headline": row["headline"],
            "context_bullets": json.loads(row["context_bullets_json"] or "[]"),
            "portfolio_bullets": json.loads(row["portfolio_bullets_json"] or "[]"),
            "watchlist_bullets": json.loads(row["watchlist_bullets_json"] or "[]"),
            "created_at": row["created_at"],
            "read": bool(row["read"]),
        }
