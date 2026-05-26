from fastapi import APIRouter

from services.market_sniper import market_sniper

router = APIRouter()


@router.get("/detections")
async def get_detections(limit: int = 50):
    return await market_sniper.get_detections(limit=limit)


@router.post("/start")
async def start_sniper():
    await market_sniper.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_sniper():
    await market_sniper.stop()
    return {"status": "stopped"}


@router.get("/status")
async def sniper_status():
    return {"running": market_sniper.is_running}
