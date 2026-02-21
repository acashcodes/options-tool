"""Portfolio CRUD routes with factory pattern."""

from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from data_provider import DataProvider
from models import PositionCreate, AssetType
import portfolio_store as store
import ocr_parser


class PositionUpdate(BaseModel):
    ticker: Optional[str] = None
    asset_type: Optional[AssetType] = None
    quantity: Optional[int] = None
    avg_cost: Optional[float] = None
    strike: Optional[float] = None
    expiration: Optional[str] = None


def create_portfolio_routes(provider: DataProvider) -> APIRouter:
    router = APIRouter(prefix="/api/portfolio")

    # Import here to avoid circular import at module level
    import portfolio_enrichment as enrichment

    @router.get("/positions")
    def list_positions():
        positions = store.load_positions()
        return {"positions": [p.model_dump() for p in positions]}

    @router.post("/positions")
    def add_position(req: PositionCreate):
        pos = store.add_position(req)
        return pos.model_dump()

    @router.put("/positions/{position_id}")
    def update_position(position_id: str, req: PositionUpdate):
        updates = req.model_dump(exclude_none=True)
        pos = store.update_position(position_id, updates)
        if pos is None:
            raise HTTPException(status_code=404, detail=f"Position '{position_id}' not found")
        return pos.model_dump()

    @router.delete("/positions/{position_id}")
    def delete_position(position_id: str):
        deleted = store.delete_position(position_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Position '{position_id}' not found")
        return {"status": "deleted", "id": position_id}

    @router.post("/import/csv")
    async def import_csv(file: UploadFile = File(...)):
        """Parse a CSV file and return candidate positions for confirmation.

        Expected columns: ticker, type (stock/call/put), quantity, avg_cost,
        strike (optional), expiration (optional).
        """
        content = await file.read()
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        reader = csv.DictReader(io.StringIO(text))
        rows = []
        errors = []
        for i, row in enumerate(reader, 1):
            # Normalise keys to lowercase, strip whitespace
            row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
            try:
                ticker = row.get("ticker") or row.get("symbol") or ""
                if not ticker:
                    errors.append(f"Row {i}: missing ticker")
                    continue

                raw_type = (row.get("type") or row.get("asset_type") or "stock").lower()
                if raw_type in ("c", "call"):
                    asset_type = "call"
                elif raw_type in ("p", "put"):
                    asset_type = "put"
                else:
                    asset_type = "stock"

                qty = int(row.get("quantity") or row.get("qty") or "1")
                cost = float(row.get("avg_cost") or row.get("cost") or row.get("price") or "0")
                strike = None
                if row.get("strike"):
                    strike = float(row["strike"])
                expiration = row.get("expiration") or row.get("expiry") or None

                rows.append({
                    "ticker": ticker.upper(),
                    "asset_type": asset_type,
                    "quantity": qty,
                    "avg_cost": cost,
                    "strike": strike,
                    "expiration": expiration,
                })
            except (ValueError, KeyError) as e:
                errors.append(f"Row {i}: {e}")

        return {"rows": rows, "errors": errors}

    @router.post("/import/confirm")
    def import_confirm(rows: list[PositionCreate]):
        """Confirm and save parsed positions (from CSV or OCR preview)."""
        positions = store.bulk_import(rows)
        return {"imported": len(positions), "positions": [p.model_dump() for p in positions]}

    @router.post("/import/ocr")
    async def import_ocr(file: UploadFile = File(...)):
        """Parse a brokerage screenshot using OCR."""
        if not ocr_parser.is_available():
            raise HTTPException(
                status_code=501,
                detail="OCR not available: install pytesseract and Pillow, and ensure Tesseract is on PATH",
            )
        content = await file.read()
        try:
            rows = ocr_parser.parse_screenshot(content)
            return {"rows": rows, "errors": []}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"OCR parsing failed: {e}")

    @router.get("/enriched")
    def get_enriched_portfolio():
        """Return fully enriched portfolio with metrics, Greeks, sector data."""
        positions = store.load_positions()
        if not positions:
            return {
                "positions": [],
                "metrics": {
                    "total_market_value": 0,
                    "total_cost_basis": 0,
                    "total_pnl": 0,
                    "total_pnl_percent": None,
                    "gross_exposure": 0,
                    "net_exposure": 0,
                    "leverage_ratio": None,
                    "position_count": 0,
                    "greeks": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "beta_weighted_delta": None},
                    "risk_flags": [],
                    "sector_breakdown": {},
                    "concentration": [],
                },
            }

        result = enrichment.enrich_portfolio(positions, provider)
        return result

    return router
