"""Assumptions endpoint: single source of truth for pricing defaults."""

from __future__ import annotations

from fastapi import APIRouter

from data_provider import DataProvider
from assumptions import get_assumptions_dict


def create_assumptions_routes(provider: DataProvider) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/assumptions")
    def get_assumptions():
        """Return the backend's current default assumptions (r, q, day-count, etc.)."""
        return get_assumptions_dict(provider)

    return router
