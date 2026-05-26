from fastapi import APIRouter

from database import get_config, set_config
from models import AgentStatus, AgentConfigUpdate
from services.agent_runner import agent_runner, _emit
from services.risk_manager import risk_manager
from services.polymarket import polymarket_service

router = APIRouter()


@router.get("/status", response_model=AgentStatus)
async def get_status():
    config = await get_config()
    return AgentStatus(
        status="running" if agent_runner.is_running else config.get("agent_status", "stopped"),
        config=config,
    )


@router.post("/start")
async def start_agent():
    await agent_runner.start()
    return {"status": "running"}


@router.post("/stop")
async def stop_agent():
    await agent_runner.stop()
    return {"status": "stopped"}


@router.post("/kill")
async def kill_switch():
    risk_manager.activate_kill_switch()
    await agent_runner.stop()
    try:
        await polymarket_service.cancel_all_orders()
    except Exception:
        pass
    await _emit("error", "KILL SWITCH ACTIVATED — all orders cancelled, agent stopped")
    return {"status": "killed", "message": "Kill switch activated. All orders cancelled."}


@router.post("/unkill")
async def deactivate_kill():
    risk_manager.deactivate_kill_switch()
    await _emit("info", "Kill switch deactivated")
    return {"status": "ready"}


@router.post("/go-live")
async def go_live():
    config = await get_config()
    if config.get("paper_mode") != "true":
        return {"paper_mode": False, "message": "Already in live mode"}
    await set_config("paper_mode", "false")
    await _emit("warning", "SWITCHED TO LIVE TRADING — real orders will be placed")
    return {"paper_mode": False, "message": "Live trading enabled. Be careful."}


@router.post("/go-paper")
async def go_paper():
    await set_config("paper_mode", "true")
    await _emit("info", "Switched to paper trading mode")
    return {"paper_mode": True, "message": "Paper trading mode enabled"}


@router.put("/config")
async def update_config(body: AgentConfigUpdate):
    updates = body.model_dump(exclude_none=True)
    for k, v in updates.items():
        await set_config(k, str(v).lower() if isinstance(v, bool) else str(v))
    await _emit("info", "Agent config updated", updates)
    return await get_config()
