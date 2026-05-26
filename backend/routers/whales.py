from fastapi import APIRouter, Query

from services.whale_conviction import whale_conviction

router = APIRouter()


@router.get("/watchlist")
async def get_watchlist(active_only: bool = True):
    return await whale_conviction.get_watchlist(active_only=active_only)


@router.post("/watchlist/refresh")
async def refresh_watchlist(
    category: str = "SPORTS",
    time_period: str = "MONTH",
    top_n: int = Query(20, ge=1, le=50),
):
    wallets = await whale_conviction.refresh_watchlist(category, time_period, top_n)
    watchlist = await whale_conviction.get_watchlist()
    return {"refreshed": len(wallets), "watchlist": watchlist}


@router.post("/watchlist/{wallet}/toggle")
async def toggle_whale(wallet: str, active: bool = True):
    await whale_conviction.toggle_whale(wallet, active)
    return {"wallet": wallet, "active": active}


@router.get("/trades")
async def get_whale_trades(limit: int = Query(50, ge=1, le=500)):
    return await whale_conviction.get_recent_whale_trades(limit=limit)


@router.get("/trades/{wallet}")
async def get_trades_for_whale(wallet: str, limit: int = Query(20, ge=1, le=100)):
    return await whale_conviction.fetch_whale_trades(wallet, limit=limit)


@router.get("/stats/{wallet}")
async def get_whale_stats(wallet: str):
    return await whale_conviction.get_whale_stats(wallet)


@router.get("/status")
async def whale_status():
    return {"running": whale_conviction.is_running}
