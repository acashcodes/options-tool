"""SQLite database setup and connection management.

Single source of truth for all persistent data: positions, marks,
watchlist, alert configuration.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from contextlib import contextmanager

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "options_tool.db"


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled."""
    _ensure_dir()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they don't exist."""
    _ensure_dir()
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_cost REAL NOT NULL,
                strike REAL,
                expiration TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                as_of_date TEXT NOT NULL,
                as_of_ts TEXT NOT NULL,
                ticker TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                strike REAL,
                expiration TEXT,
                mark_price REAL NOT NULL,
                mark_source TEXT NOT NULL DEFAULT 'mid'
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_marks_unique
                ON marks(as_of_date, ticker, asset_type, strike, expiration);

            CREATE INDEX IF NOT EXISTS idx_marks_date
                ON marks(as_of_date);

            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS alert_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dismissed_alerts (
                alert_id TEXT PRIMARY KEY
            );
        """)


def migrate_from_json() -> None:
    """Migrate data from JSON files to SQLite if DB is empty and JSON files exist."""
    import json

    portfolio_json = DATA_DIR / "portfolio.json"
    watchlist_json = DATA_DIR / "watchlist.json"
    alerts_json = DATA_DIR / "alerts_config.json"

    with get_db() as conn:
        # Migrate positions
        count = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        if count == 0 and portfolio_json.exists():
            try:
                positions = json.loads(portfolio_json.read_text())
                for p in positions:
                    conn.execute(
                        """INSERT OR IGNORE INTO positions
                           (id, ticker, asset_type, quantity, avg_cost, strike, expiration)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (p.get("id", ""), p["ticker"], p["asset_type"],
                         p["quantity"], p["avg_cost"], p.get("strike"),
                         p.get("expiration")),
                    )
            except Exception:
                pass

        # Migrate watchlist
        count = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        if count == 0 and watchlist_json.exists():
            try:
                tickers = json.loads(watchlist_json.read_text())
                for t in tickers:
                    if isinstance(t, str):
                        conn.execute(
                            "INSERT OR IGNORE INTO watchlist (ticker) VALUES (?)",
                            (t.upper(),),
                        )
            except Exception:
                pass

        # Migrate alerts config
        count = conn.execute("SELECT COUNT(*) FROM alert_config").fetchone()[0]
        if count == 0 and alerts_json.exists():
            try:
                data = json.loads(alerts_json.read_text())
                thresholds = data.get("thresholds", {})
                for k, v in thresholds.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO alert_config (key, value) VALUES (?, ?)",
                        (k, json.dumps(v)),
                    )
                for alert_id in data.get("dismissed", []):
                    conn.execute(
                        "INSERT OR IGNORE INTO dismissed_alerts (alert_id) VALUES (?)",
                        (alert_id,),
                    )
            except Exception:
                pass
