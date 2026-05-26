from fastapi import APIRouter

from services.live_scalper import live_scalper
from services.position_manager import position_manager

router = APIRouter()


@router.get("/positions")
async def get_positions(status: str = "", limit: int = 50):
    return await position_manager.get_positions(
        status=status or None,
        strategy="live_scalper",
        limit=limit,
    )


@router.get("/signals")
async def get_signals():
    return live_scalper.get_all_signals()


@router.post("/start")
async def start_scalper():
    await live_scalper.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_scalper():
    await live_scalper.stop()
    return {"status": "stopped"}


@router.get("/status")
async def scalper_status():
    return {"running": live_scalper.is_running}
