"""Portfolio store — delegates to SQLite repository.

Maintains the same public interface so routes don't need changes.
"""

from __future__ import annotations

from typing import Optional
from models import Position, PositionCreate
from repositories.portfolio_repo import (
    load_positions,
    add_position,
    update_position,
    delete_position,
    bulk_import,
)

# Re-export all functions — routes import from portfolio_store
__all__ = [
    "load_positions",
    "add_position",
    "update_position",
    "delete_position",
    "bulk_import",
]
