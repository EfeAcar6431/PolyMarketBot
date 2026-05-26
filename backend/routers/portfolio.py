from fastapi import APIRouter

from database import get_db
from services.polymarket import polymarket_service
from models import PortfolioSummary

router = APIRouter()


@router.get("", response_model=PortfolioSummary)
async def get_portfolio():
    balance = await polymarket_service.get_balance()
    positions = await polymarket_service.get_positions()

    db = await get_db()
    try:
        cursor = await db.execute("SELECT COALESCE(SUM(pnl), 0) as total FROM trades")
        row = await cursor.fetchone()
        total_pnl = float(row["total"])

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM trades WHERE pnl > 0")
        wins = (await cursor.fetchone())["cnt"]

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM trades WHERE pnl != 0")
        settled = (await cursor.fetchone())["cnt"]
    finally:
        await db.close()

    win_rate = (wins / settled * 100) if settled > 0 else 0.0

    return PortfolioSummary(
        balance=balance,
        total_pnl=total_pnl,
        active_positions=len(positions) if isinstance(positions, list) else 0,
        win_rate=round(win_rate, 1),
        positions=positions if isinstance(positions, list) else [],
    )


@router.get("/balance")
async def get_balance():
    balance = await polymarket_service.get_balance()
    return {"balance": balance}
