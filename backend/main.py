from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import markets, portfolio, agent, trades, ws, whales, sentiment, market_making, odds, scalper, sniper, agent_plans


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="PolyMarketBot API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(markets.router, prefix="/api/markets", tags=["markets"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(whales.router, prefix="/api/whales", tags=["whales"])
app.include_router(sentiment.router, prefix="/api/sentiment", tags=["sentiment"])
app.include_router(market_making.router, prefix="/api/market-making", tags=["market-making"])
app.include_router(odds.router, prefix="/api/odds", tags=["odds"])
app.include_router(scalper.router, prefix="/api/scalper", tags=["scalper"])
app.include_router(sniper.router, prefix="/api/sniper", tags=["sniper"])
app.include_router(agent_plans.router, prefix="/api/agent-plans", tags=["agent-plans"])
app.include_router(ws.router, tags=["websocket"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
