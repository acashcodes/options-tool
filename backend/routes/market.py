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

    @router.get("/options/analytics/{symbol}")
    def get_options_analytics(symbol: str):
        """Compute IV term structure, skew, expected moves, and flow for a symbol."""
        from datetime import datetime, date
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            expirations = provider.get_options_expirations(symbol)
            if not expirations:
                raise HTTPException(
                    status_code=404, detail=f"No options for '{symbol}'"
                )

            # Use max 8 nearest expirations
            exps = expirations[:8]

            # Fetch chains in parallel
            chains = {}

            def fetch_chain(exp):
                try:
                    return exp, provider.get_options_chain(symbol, exp)
                except Exception:
                    return exp, None

            with ThreadPoolExecutor(max_workers=6) as executor:
                futs = [executor.submit(fetch_chain, exp) for exp in exps]
                for fut in as_completed(futs):
                    exp, chain = fut.result()
                    if chain:
                        chains[exp] = chain

            underlying = None
            for exp in exps:
                if exp in chains and chains[exp].get("underlying_price"):
                    underlying = chains[exp]["underlying_price"]
                    break

            if not underlying:
                raise HTTPException(
                    status_code=404, detail="Could not determine underlying price"
                )

            today = date.today()

            expected_moves = []
            iv_term_structure = []
            total_call_vol = 0
            total_put_vol = 0
            total_call_oi = 0
            total_put_oi = 0
            unusual_activity = []

            # For skew: use nearest expiration
            skew_data = {
                "expiration": None,
                "strikes": [],
                "call_iv": [],
                "put_iv": [],
            }

            for exp in exps:
                if exp not in chains:
                    continue
                chain = chains[exp]
                calls = chain.get("calls", [])
                puts = chain.get("puts", [])

                # Compute DTE
                try:
                    exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                    dte = (exp_date - today).days
                except Exception:
                    continue
                if dte < 0:
                    continue

                # Find ATM options (closest strike to underlying)
                atm_call = (
                    min(calls, key=lambda c: abs(c["strike"] - underlying), default=None)
                    if calls
                    else None
                )
                atm_put = (
                    min(puts, key=lambda p: abs(p["strike"] - underlying), default=None)
                    if puts
                    else None
                )

                # ATM IV
                atm_iv = None
                if atm_call and atm_put:
                    c_iv = atm_call.get("impliedVolatility") or atm_call.get("iv")
                    p_iv = atm_put.get("impliedVolatility") or atm_put.get("iv")
                    if c_iv and p_iv:
                        atm_iv = (c_iv + p_iv) / 2
                    elif c_iv:
                        atm_iv = c_iv
                    elif p_iv:
                        atm_iv = p_iv

                if atm_iv:
                    iv_term_structure.append(
                        {
                            "expiration": exp,
                            "dte": dte,
                            "atm_iv": round(
                                atm_iv * 100 if atm_iv < 5 else atm_iv, 1
                            ),
                        }
                    )

                # Expected move: ATM straddle mid / underlying
                if atm_call and atm_put:
                    c_mid = atm_call.get("lastPrice") or atm_call.get("mid") or 0
                    p_mid = atm_put.get("lastPrice") or atm_put.get("mid") or 0
                    if c_mid and p_mid:
                        straddle = c_mid + p_mid
                        exp_move_pct = (straddle / underlying) * 100
                        expected_moves.append(
                            {
                                "expiration": exp,
                                "dte": dte,
                                "straddle_price": round(straddle, 2),
                                "expected_move_pct": round(exp_move_pct, 1),
                                "expected_move_dollar": round(straddle, 2),
                            }
                        )

                # Aggregate volume and OI
                for c in calls:
                    vol = c.get("volume") or 0
                    oi = c.get("openInterest") or 0
                    total_call_vol += vol
                    total_call_oi += oi
                    if oi > 0 and vol > 3 * oi:
                        unusual_activity.append(
                            {
                                "type": "call",
                                "strike": c["strike"],
                                "expiration": exp,
                                "volume": vol,
                                "oi": oi,
                                "ratio": round(vol / oi, 1),
                            }
                        )
                for p in puts:
                    vol = p.get("volume") or 0
                    oi = p.get("openInterest") or 0
                    total_put_vol += vol
                    total_put_oi += oi
                    if oi > 0 and vol > 3 * oi:
                        unusual_activity.append(
                            {
                                "type": "put",
                                "strike": p["strike"],
                                "expiration": exp,
                                "volume": vol,
                                "oi": oi,
                                "ratio": round(vol / oi, 1),
                            }
                        )

                # Skew for nearest expiry
                if skew_data["expiration"] is None:
                    skew_data["expiration"] = exp
                    # Get IVs across strikes for this expiry
                    # Filter strikes to +/- 20% of underlying
                    lo = underlying * 0.8
                    hi = underlying * 1.2
                    call_map = {
                        c["strike"]: c for c in calls if lo <= c["strike"] <= hi
                    }
                    put_map = {
                        p["strike"]: p for p in puts if lo <= p["strike"] <= hi
                    }
                    all_strikes = sorted(
                        set(list(call_map.keys()) + list(put_map.keys()))
                    )

                    for strike in all_strikes:
                        c_iv_val = None
                        p_iv_val = None
                        if strike in call_map:
                            raw = call_map[strike].get(
                                "impliedVolatility"
                            ) or call_map[strike].get("iv")
                            if raw:
                                c_iv_val = round(
                                    raw * 100 if raw < 5 else raw, 1
                                )
                        if strike in put_map:
                            raw = put_map[strike].get(
                                "impliedVolatility"
                            ) or put_map[strike].get("iv")
                            if raw:
                                p_iv_val = round(
                                    raw * 100 if raw < 5 else raw, 1
                                )

                        if c_iv_val or p_iv_val:
                            skew_data["strikes"].append(strike)
                            skew_data["call_iv"].append(c_iv_val)
                            skew_data["put_iv"].append(p_iv_val)

            # Flow summary
            pc_ratio_vol = (
                round(total_put_vol / total_call_vol, 2)
                if total_call_vol > 0
                else None
            )
            pc_ratio_oi = (
                round(total_put_oi / total_call_oi, 2)
                if total_call_oi > 0
                else None
            )

            # Sort unusual activity by ratio desc, top 10
            unusual_activity.sort(key=lambda x: x["ratio"], reverse=True)
            unusual_activity = unusual_activity[:10]

            return {
                "symbol": symbol.upper(),
                "underlying_price": underlying,
                "expected_moves": expected_moves,
                "iv_term_structure": iv_term_structure,
                "skew": skew_data,
                "flow": {
                    "total_call_volume": total_call_vol,
                    "total_put_volume": total_put_vol,
                    "total_call_oi": total_call_oi,
                    "total_put_oi": total_put_oi,
                    "pc_ratio_volume": pc_ratio_vol,
                    "pc_ratio_oi": pc_ratio_oi,
                    "unusual_activity": unusual_activity,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Analytics failed for '{symbol}': {e}",
            )

    return router
