"""OCR-based portfolio import from screenshots.

Uses pytesseract (optional dependency). Returns a graceful error
if Tesseract is not installed on the system.
"""

from __future__ import annotations

import io
import re
from typing import Optional

from models import PositionCreate, AssetType

# Flag set at import time
_TESSERACT_AVAILABLE = False
try:
    import pytesseract
    from PIL import Image
    _TESSERACT_AVAILABLE = True
except ImportError:
    pass


def is_available() -> bool:
    return _TESSERACT_AVAILABLE


def parse_screenshot(image_bytes: bytes) -> list[dict]:
    """Parse a brokerage screenshot into candidate position rows.

    Returns list of dicts with keys: ticker, asset_type, quantity, avg_cost,
    strike, expiration.  Values may be None if not parseable.
    """
    if not _TESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract/Pillow not installed")

    img = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(img)

    rows = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parsed = _parse_line(line)
        if parsed:
            rows.append(parsed)
    return rows


def _parse_line(line: str) -> Optional[dict]:
    """Attempt to extract a position from a single OCR line."""
    # Try to match patterns like: AAPL 100 @ 150.00
    # or: AAPL 150C 03/21/25 10 @ 3.50
    tokens = line.split()
    if len(tokens) < 3:
        return None

    ticker = tokens[0].upper()
    if not re.match(r'^[A-Z]{1,5}$', ticker):
        return None

    # Look for option pattern: strike + C/P
    strike = None
    option_type = None
    expiration = None
    quantity = None
    avg_cost = None

    for i, tok in enumerate(tokens[1:], 1):
        # Option strike: "150C" or "150P"
        m = re.match(r'^(\d+\.?\d*)(C|P)$', tok, re.IGNORECASE)
        if m:
            strike = float(m.group(1))
            option_type = "call" if m.group(2).upper() == "C" else "put"
            continue

        # Date: MM/DD/YY or YYYY-MM-DD
        if re.match(r'^\d{2}/\d{2}/\d{2,4}$', tok):
            parts = tok.split("/")
            if len(parts[2]) == 2:
                parts[2] = "20" + parts[2]
            expiration = f"{parts[2]}-{parts[0]}-{parts[1]}"
            continue
        if re.match(r'^\d{4}-\d{2}-\d{2}$', tok):
            expiration = tok
            continue

        # Quantity (integer, possibly negative)
        if quantity is None and re.match(r'^-?\d+$', tok):
            quantity = int(tok)
            continue

        # Price after @
        if tok == "@" and i + 1 < len(tokens):
            try:
                avg_cost = float(tokens[i + 1])
            except ValueError:
                pass
            continue

        # Standalone float could be avg_cost
        if avg_cost is None:
            try:
                avg_cost = float(tok)
            except ValueError:
                pass

    if quantity is None:
        quantity = 1
    if avg_cost is None:
        avg_cost = 0.0

    asset_type = "stock"
    if option_type:
        asset_type = option_type

    return {
        "ticker": ticker,
        "asset_type": asset_type,
        "quantity": quantity,
        "avg_cost": avg_cost,
        "strike": strike,
        "expiration": expiration,
    }
