from fastapi import APIRouter, HTTPException, Query

from data_provider import DataProvider

router = APIRouter(prefix="/api")


def create_market_routes(provider: DataProvider) -> APIRouter:
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

    return router
