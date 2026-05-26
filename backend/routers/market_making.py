from fastapi import APIRouter
from pydantic import BaseModel

from services.market_maker import market_maker

router = APIRouter()


class AddMarketBody(BaseModel):
    token_id: str
    condition_id: str = ""
    title: str = ""
    spread: float = 0.04


class UpdateSpreadBody(BaseModel):
    spread: float


@router.get("/inventory")
async def get_inventory():
    return await market_maker.get_all_inventory()


@router.post("/add")
async def add_market(body: AddMarketBody):
    await market_maker.add_market(
        token_id=body.token_id,
        condition_id=body.condition_id,
        title=body.title,
        spread=body.spread,
    )
    return {"status": "added", "token_id": body.token_id}


@router.post("/remove/{token_id}")
async def remove_market(token_id: str):
    await market_maker.remove_market(token_id)
    return {"status": "removed", "token_id": token_id}


@router.put("/spread/{token_id}")
async def update_spread(token_id: str, body: UpdateSpreadBody):
    await market_maker.update_spread(token_id, body.spread)
    return {"status": "updated", "token_id": token_id, "spread": body.spread}


@router.post("/cycle")
async def trigger_cycle():
    from database import get_config
    config = await get_config()
    results = await market_maker.run_cycle(config)
    return {"results": results}
