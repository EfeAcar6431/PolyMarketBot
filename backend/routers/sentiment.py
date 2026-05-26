from fastapi import APIRouter, Query

from services.sentiment_monitor import sentiment_monitor

router = APIRouter()


@router.get("/alerts")
async def get_alerts(limit: int = Query(50, ge=1, le=500)):
    return await sentiment_monitor.get_recent_alerts(limit=limit)
