"""JSON-file persistence layer for portfolio positions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from models import Position, PositionCreate

DATA_DIR = Path(__file__).parent / "data"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_positions() -> list[Position]:
    _ensure_dir()
    if not PORTFOLIO_FILE.exists():
        return []
    try:
        raw = json.loads(PORTFOLIO_FILE.read_text())
        return [Position(**p) for p in raw]
    except (json.JSONDecodeError, Exception):
        return []


def save_positions(positions: list[Position]) -> None:
    _ensure_dir()
    data = [p.model_dump() for p in positions]
    PORTFOLIO_FILE.write_text(json.dumps(data, indent=2))


def add_position(create: PositionCreate) -> Position:
    positions = load_positions()
    pos = Position(**create.model_dump())
    positions.append(pos)
    save_positions(positions)
    return pos


def update_position(position_id: str, updates: dict) -> Optional[Position]:
    positions = load_positions()
    for i, p in enumerate(positions):
        if p.id == position_id:
            data = p.model_dump()
            data.update({k: v for k, v in updates.items() if v is not None})
            positions[i] = Position(**data)
            save_positions(positions)
            return positions[i]
    return None


def delete_position(position_id: str) -> bool:
    positions = load_positions()
    new_positions = [p for p in positions if p.id != position_id]
    if len(new_positions) == len(positions):
        return False
    save_positions(new_positions)
    return True


def bulk_import(creates: list[PositionCreate]) -> list[Position]:
    positions = load_positions()
    new_positions = [Position(**c.model_dump()) for c in creates]
    positions.extend(new_positions)
    save_positions(positions)
    return new_positions
