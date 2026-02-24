"""Pydantic models for strategy analysis requests/responses."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal, Optional


Instrument = Literal["option", "stock"]
OptionType = Literal["call", "put"]
Action = Literal["buy", "sell"]


class Underlying(BaseModel):
    symbol: Optional[str] = None
    price: float
    dividend_yield: float = 0.0  # decimal


class PricingAssumptions(BaseModel):
    risk_free_rate: float = 0.045  # decimal
    dividend_yield: float = 0.0
    model: Literal["BSM"] = "BSM"
    day_count: Literal["ACT/365"] = "ACT/365"


class StrategyLeg(BaseModel):
    instrument: Instrument
    action: Action
    quantity: float  # contracts for options, shares for stock
    entry_price: float  # per share
    # Option fields
    option_type: Optional[OptionType] = None
    strike: Optional[float] = None
    expiration: Optional[str] = None  # YYYY-MM-DD
    iv: Optional[float] = None  # decimal (0.30)
    multiplier: int = 100
    bid: Optional[float] = None
    ask: Optional[float] = None
    entry_price_override: Optional[float] = None


class AnalyzeRequest(BaseModel):
    underlying: Underlying
    assumptions: Optional[PricingAssumptions] = None
    legs: list[StrategyLeg]
    pricing_mode: str = "mid"
    slippage_pct_of_spread: float = 0.0
    curve_points: int = 200
    days_forward: int = 0
