"""Simple in-memory TTL cache. No external dependencies."""

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    """Thread-unsafe TTL cache (fine for single-process FastAPI with uvicorn)."""

    def __init__(self, ttl_seconds: float):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if not item:
            return None
        ts, val = item
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, val: Any) -> None:
        self._store[key] = (time.time(), val)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
