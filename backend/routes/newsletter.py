"""Newsletter API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from newsletter.service import NewsletterService
from newsletter.config import load_config


class MarkReadRequest(BaseModel):
    issue_id: str


def create_newsletter_routes(service: Optional[NewsletterService] = None) -> APIRouter:
    router = APIRouter(prefix="/api/newsletter")

    def _svc() -> NewsletterService:
        if service is None:
            raise HTTPException(status_code=503, detail="Newsletter feature is disabled")
        return service

    @router.get("/latest")
    def get_latest():
        svc = _svc()
        issue = svc.get_latest()
        if not issue:
            return {"issue": None}
        return {"issue": issue}

    @router.get("/issues/{issue_id}")
    def get_issue(issue_id: str):
        svc = _svc()
        issue = svc.get_issue_full(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        return {"issue": issue}

    @router.get("/history")
    def get_history(limit: int = 50, offset: int = 0):
        svc = _svc()
        issues = svc.get_history(limit=limit, offset=offset)
        return {"issues": issues}

    @router.post("/mark_read")
    def mark_read(req: MarkReadRequest):
        svc = _svc()
        success = svc.mark_read(req.issue_id)
        if not success:
            raise HTTPException(status_code=404, detail="Issue not found")
        return {"success": True}

    @router.post("/sync_now")
    def sync_now():
        """Trigger an immediate IMAP fetch."""
        svc = _svc()
        # We need access to the listener — import from main module state
        from newsletter.imap_listener import IMAPListener
        import portfolio_store as port_store
        import watchlist_store as wl_store

        config = svc.config
        portfolio_tickers = list({p.ticker.upper() for p in port_store.load_positions()})
        watchlist_tickers = wl_store.load_watchlist()

        def on_email(raw_bytes: bytes):
            svc.process_raw_email(raw_bytes, portfolio_tickers, watchlist_tickers)

        listener = IMAPListener(config, on_email)
        count = listener.fetch_unseen_once()
        return {"processed": count}

    return router
