from fastapi import APIRouter, Query

from services.polymarket import polymarket_service
from services.llm_analyzer import llm_analyzer

router = APIRouter()


@router.get("")
async def list_markets(
    query: str = "",
    tag: str = "",
    sort_by: str = "volume24hr",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await polymarket_service.search_markets(
        query=query, tag=tag, sort_by=sort_by, limit=limit, offset=offset
    )


@router.get("/tags")
async def list_tags():
    return await polymarket_service.get_tags()


@router.get("/{condition_id}")
async def get_market(condition_id: str):
    return await polymarket_service.get_market(condition_id)


@router.get("/{condition_id}/orderbook")
async def get_orderbook(condition_id: str, token_id: str):
    return await polymarket_service.get_orderbook(token_id)


@router.get("/{condition_id}/history")
async def get_price_history(
    condition_id: str,
    token_id: str,
    interval: str = "max",
    fidelity: int = 100,
):
    return await polymarket_service.get_price_history(token_id, interval, fidelity)


@router.post("/{condition_id}/analyze")
async def analyze_market(condition_id: str):
    market = await polymarket_service.get_market(condition_id)
    tokens = market.get("tokens", [])
    price = 0.5
    for t in tokens:
        if t.get("outcome", "").lower() == "yes":
            price = float(t.get("price", 0.5))
            break

    if price == 0.5 and market.get("outcomePrices"):
        try:
            prices = market["outcomePrices"]
            if isinstance(prices, str):
                import json
                prices = json.loads(prices)
            price = float(prices[0])
        except Exception:
            pass

    analysis = await llm_analyzer.analyze_market(
        question=market.get("question", ""),
        current_price=price,
        description=market.get("description", ""),
    )
    return {
        "market_id": condition_id,
        "question": market.get("question", ""),
        "current_price": price,
        **analysis,
    }
