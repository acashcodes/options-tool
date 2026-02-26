import logging
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env from repo root (one level up from backend/)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from data_provider import YFinanceProvider
from routes.market import create_market_routes
from routes.portfolio import create_portfolio_routes
from routes.dashboard import create_dashboard_routes
from routes.recommender import create_recommender_routes
from routes.strategy import create_strategy_routes
from routes.assumptions import create_assumptions_routes
from routes.valuations import create_valuations_routes
from routes.newsletter import create_newsletter_routes
from db import init_db, migrate_from_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize SQLite database and migrate from JSON if needed
init_db()
migrate_from_json()

# Initialize newsletter service (if enabled via env vars)
newsletter_service = None
newsletter_listener = None
try:
    from newsletter.config import load_config as load_newsletter_config
    from newsletter.service import NewsletterService
    from newsletter.imap_listener import IMAPListener
    import portfolio_store as port_store
    import watchlist_store as wl_store

    nl_config = load_newsletter_config()
    if nl_config.enabled and nl_config.encryption_key:
        newsletter_service = NewsletterService(nl_config)
        logger.info("Newsletter service initialized")

        # Start IMAP listener in background
        if nl_config.imap_username and nl_config.imap_password:
            def _on_new_email(raw_bytes: bytes):
                portfolio_tickers = list({p.ticker.upper() for p in port_store.load_positions()})
                watchlist_tickers = wl_store.load_watchlist()
                newsletter_service.process_raw_email(raw_bytes, portfolio_tickers, watchlist_tickers)

            newsletter_listener = IMAPListener(nl_config, _on_new_email)
            newsletter_listener.start()
            logger.info("IMAP listener started")
    else:
        logger.info("Newsletter feature disabled (NEWSLETTER_ENABLED != true or missing encryption key)")
except Exception as exc:
    logger.warning("Newsletter initialization skipped: %s", exc)

app = FastAPI(title="Options Strategy Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

provider = YFinanceProvider()
app.include_router(create_market_routes(provider))
app.include_router(create_portfolio_routes(provider))
app.include_router(create_dashboard_routes(provider, newsletter_service=newsletter_service))
app.include_router(create_recommender_routes(provider))
app.include_router(create_strategy_routes(provider))
app.include_router(create_assumptions_routes(provider))
app.include_router(create_valuations_routes(provider))
app.include_router(create_newsletter_routes(service=newsletter_service))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.on_event("shutdown")
def shutdown():
    if newsletter_listener:
        newsletter_listener.stop()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
