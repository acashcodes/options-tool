"""Pydantic models for portfolio management."""

from __future__ import annotations

from datetime import date
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field
import uuid


class AssetType(str, Enum):
    STOCK = "stock"
    CALL = "call"
    PUT = "put"


class PositionCreate(BaseModel):
    """Schema for creating a new position."""
    ticker: str
    asset_type: AssetType
    quantity: int
    avg_cost: float
    strike: Optional[float] = None
    expiration: Optional[str] = None  # YYYY-MM-DD


class Position(PositionCreate):
    """A stored portfolio position with an ID."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])


class EnrichedPosition(BaseModel):
    """A position enriched with live market data and Greeks."""
    id: str
    ticker: str
    asset_type: AssetType
    quantity: int
    avg_cost: float
    strike: Optional[float] = None
    expiration: Optional[str] = None
    # Live data
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    cost_basis: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    # Greeks (dollar terms per position)
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    # Sector info
    sector: Optional[str] = None
    beta: Optional[float] = None
    weight: Optional[float] = None


class PortfolioGreeks(BaseModel):
    """Aggregated portfolio-level Greeks in dollar terms."""
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    beta_weighted_delta: Optional[float] = None


class PortfolioMetrics(BaseModel):
    """Portfolio-level summary metrics."""
    total_market_value: float = 0.0
    total_cost_basis: float = 0.0
    total_pnl: float = 0.0
    total_pnl_percent: Optional[float] = None
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    leverage_ratio: Optional[float] = None
    position_count: int = 0
    greeks: PortfolioGreeks = PortfolioGreeks()
    risk_flags: list[str] = []
    sector_breakdown: dict[str, float] = {}
    concentration: list[dict] = []
