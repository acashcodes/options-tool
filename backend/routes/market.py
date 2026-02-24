from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from data_provider import DataProvider
from greeks import compute_greeks, bs_price, prob_itm

router = APIRouter(prefix="/api")


class GreeksRequest(BaseModel):
    S: float
    K: float
    t: float  # time to expiry in years
    r: float = 0.045
    sigma: float  # annualised decimal (e.g. 0.30)
    option_type: str = "call"
    q: float = 0.0  # dividend yield


class BatchGreeksLeg(BaseModel):
    S: float
    K: float
    t: float
    r: float = 0.045
    sigma: float
    option_type: str = "call"
    q: float = 0.0


class BatchGreeksRequest(BaseModel):
    legs: List[BatchGreeksLeg]
    price_points: List[float]


def create_market_routes(provider: DataProvider) -> APIRouter:
    @router.get("/history/{symbol}")
    def get_history(symbol: str, period: str = Query("1y"), interval: str = Query("1d")):
        try:
            history = provider.get_history(symbol, period=period, interval=interval)
            return {"symbol": symbol.upper(), "history": history}
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Could not fetch history for '{symbol}': {e}")

    @router.get("/quote/{symbol}")
    def get_quote(symbol: str):
        try:
            return provider.get_quote(symbol)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Could not fetch quote for '{symbol}': {e}")

    @router.get("/options/expirations/{symbol}")
    def get_expirations(symbol: str):
        try:
            expirations = provider.get_options_expirations(symbol)
            if not expirations:
                raise HTTPException(status_code=404, detail=f"No options available for '{symbol}'")
            return {"symbol": symbol.upper(), "expirations": expirations}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Could not fetch expirations for '{symbol}': {e}")

    @router.get("/options/chain/{symbol}")
    def get_chain(
        symbol: str,
        expiration: str = Query(..., description="Expiration date YYYY-MM-DD"),
        strike_range_pct: Optional[float] = Query(None, description="Filter strikes within +/-% of underlying"),
        min_strike: Optional[float] = Query(None),
        max_strike: Optional[float] = Query(None),
    ):
        try:
            chain = provider.get_options_chain(symbol, expiration)

            # Backend strike filtering
            underlying_price = chain.get("underlying_price")
            if underlying_price and strike_range_pct is not None:
                lo = underlying_price * (1 - strike_range_pct)
                hi = underlying_price * (1 + strike_range_pct)
                chain["calls"] = [c for c in chain.get("calls", []) if lo <= c["strike"] <= hi]
                chain["puts"] = [p for p in chain.get("puts", []) if lo <= p["strike"] <= hi]
            elif min_strike is not None or max_strike is not None:
                lo = min_strike or 0
                hi = max_strike or float("inf")
                chain["calls"] = [c for c in chain.get("calls", []) if lo <= c["strike"] <= hi]
                chain["puts"] = [p for p in chain.get("puts", []) if lo <= p["strike"] <= hi]

            return {"symbol": symbol.upper(), "expiration": expiration, **chain}
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Could not fetch chain for '{symbol}' at {expiration}: {e}")

    @router.post("/greeks")
    def calc_greeks(req: GreeksRequest):
        """Compute Greeks for a single option."""
        try:
            result = compute_greeks(req.S, req.K, req.t, req.r, req.sigma, req.option_type, q=req.q)
            result["prob_itm"] = prob_itm(req.S, req.K, req.t, req.r, req.sigma, req.option_type, q=req.q)
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # NOTE: /greeks/payoff-curve has been removed (WP2.5).
    # Use POST /api/strategy/analyze for correct P&L curves with proper
    # sign conventions, entry costs, and multi-leg support.

    @router.get("/technicals/{symbol}")
    def get_technicals(symbol: str):
        """Compute moving averages and technical indicators for a symbol."""
        try:
            history = provider.get_history(symbol, period="1y", interval="1d")
            if not history:
                return {"symbol": symbol.upper(), "moving_averages": []}

            closes = [h["close"] for h in history if h.get("close") is not None]
            if len(closes) < 5:
                return {"symbol": symbol.upper(), "moving_averages": []}

            current_price = closes[-1]
            ma_periods = [
                {"period": 5, "label": "5 DMA"},
                {"period": 20, "label": "20 DMA"},
                {"period": 50, "label": "50 DMA"},
                {"period": 200, "label": "200 DMA"},
            ]

            moving_averages = []
            for ma in ma_periods:
                n = ma["period"]
                if len(closes) >= n:
                    ma_val = sum(closes[-n:]) / n
                    pct_diff = ((current_price - ma_val) / ma_val) * 100
                    moving_averages.append({
                        "period": n,
                        "label": ma["label"],
                        "value": round(ma_val, 2),
                        "above": current_price >= ma_val,
                        "pct_distance": round(pct_diff, 2),
                    })
                else:
                    moving_averages.append({
                        "period": n,
                        "label": ma["label"],
                        "value": None,
                        "above": None,
                        "pct_distance": None,
                    })

            return {
                "symbol": symbol.upper(),
                "current_price": round(current_price, 2),
                "moving_averages": moving_averages,
            }
        except Exception as e:
            raise HTTPException(
                status_code=404,
                detail=f"Could not compute technicals for '{symbol}': {e}",
            )

    return router
