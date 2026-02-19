import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_provider import YFinanceProvider
from routes.market import create_market_routes

app = FastAPI(title="Options Strategy Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

provider = YFinanceProvider()
app.include_router(create_market_routes(provider))


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
