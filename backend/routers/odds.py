from fastapi import APIRouter

from database import get_config
from services.odds_comparator import odds_comparator

router = APIRouter()


@router.get("/discrepancies")
async def get_discrepancies():
    config = await get_config()
    return await odds_comparator.get_cached_discrepancies(config)


@router.post("/refresh")
async def refresh_odds():
    odds_comparator._cache.clear()
    config = await get_config()
    results = await odds_comparator.get_cached_discrepancies(config)
    return {"refreshed": True, "discrepancies": len(results), "results": results}


@router.get("/sports")
async def list_sports():
    return await odds_comparator.get_available_sports()
