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


class BatchGreeksLeg(BaseModel):
    S: float
    K: float
    t: float
    r: float = 0.045
    sigma: float
    option_type: str = "call"


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
    def get_chain(symbol: str, expiration: str = Query(..., description="Expiration date YYYY-MM-DD")):
        try:
            chain = provider.get_options_chain(symbol, expiration)
            return {"symbol": symbol.upper(), "expiration": expiration, **chain}
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Could not fetch chain for '{symbol}' at {expiration}: {e}")

    @router.post("/greeks")
    def calc_greeks(req: GreeksRequest):
        """Compute Greeks for a single option."""
        try:
            result = compute_greeks(req.S, req.K, req.t, req.r, req.sigma, req.option_type)
            result["prob_itm"] = round(prob_itm(req.S, req.K, req.t, req.r, req.sigma, req.option_type), 4)
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/greeks/payoff-curve")
    def calc_payoff_curve(req: BatchGreeksRequest):
        """Compute pre-expiration P&L curve for a multi-leg strategy.

        For each price point, computes the theoretical value of the position
        using BS pricing, minus the entry cost.
        """
        try:
            results = []
            for price in req.price_points:
                total_value = 0.0
                for leg in req.legs:
                    option_price = bs_price(price, leg.K, leg.t, leg.r, leg.sigma, leg.option_type)
                    total_value += option_price
                results.append({"price": round(price, 2), "value": round(total_value, 4)})
            return {"curve": results}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return router
