"""Portfolio positions repository — SQLite backed."""

from __future__ import annotations

from typing import Optional
from datetime import datetime

from db import get_db
from models import Position, PositionCreate


def load_positions() -> list[Position]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, ticker, asset_type, quantity, avg_cost, strike, expiration FROM positions"
        ).fetchall()
    return [
        Position(
            id=r["id"], ticker=r["ticker"], asset_type=r["asset_type"],
            quantity=int(r["quantity"]), avg_cost=r["avg_cost"],
            strike=r["strike"], expiration=r["expiration"],
        )
        for r in rows
    ]


def add_position(create: PositionCreate) -> Position:
    pos = Position(**create.model_dump())
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO positions (id, ticker, asset_type, quantity, avg_cost, strike, expiration, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pos.id, pos.ticker, pos.asset_type.value, pos.quantity,
             pos.avg_cost, pos.strike, pos.expiration, now, now),
        )
    return pos


def update_position(position_id: str, updates: dict) -> Optional[Position]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, ticker, asset_type, quantity, avg_cost, strike, expiration FROM positions WHERE id=?",
            (position_id,),
        ).fetchone()
        if not row:
            return None

        data = dict(row)
        data.update({k: v for k, v in updates.items() if v is not None})
        now = datetime.utcnow().isoformat()
        conn.execute(
            """UPDATE positions SET ticker=?, asset_type=?, quantity=?, avg_cost=?,
               strike=?, expiration=?, updated_at=? WHERE id=?""",
            (data["ticker"], data["asset_type"], data["quantity"], data["avg_cost"],
             data.get("strike"), data.get("expiration"), now, position_id),
        )
    return Position(**data)


def delete_position(position_id: str) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM positions WHERE id=?", (position_id,))
    return cursor.rowcount > 0


def bulk_import(creates: list[PositionCreate]) -> list[Position]:
    positions = []
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        for c in creates:
            pos = Position(**c.model_dump())
            conn.execute(
                """INSERT INTO positions (id, ticker, asset_type, quantity, avg_cost, strike, expiration, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pos.id, pos.ticker, pos.asset_type.value, pos.quantity,
                 pos.avg_cost, pos.strike, pos.expiration, now, now),
            )
            positions.append(pos)
    return positions
