# Options Strategy Analyzer

## Session End Protocol
Before ending any session, ALWAYS:
1. Commit all work in the current worktree
2. Merge the worktree branch into `feature/newsletter-imap-dashboard` in the main repo
3. Ensure the main repo HEAD has the latest code

## Servers
- Backend: `cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- Frontend: `cd frontend && npx vite --port 3000`

## Architecture
- Backend: Python FastAPI + yfinance + Black-Scholes (scipy) + SQLite
- Frontend: React 19 + Vite + Recharts
- Database: SQLite with WAL mode (backend/data/)
- Data files (*.db, *.json in backend/data/) are local-only, never committed
