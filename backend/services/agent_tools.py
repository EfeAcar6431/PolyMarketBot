"""Tools the LLM trading agent can invoke mid-reasoning.

Each tool has:
  - An OpenAI function-calling schema (TOOL_SCHEMAS)
  - An async handler (TOOL_HANDLERS)
"""

import json
import logging

from services.polymarket import polymarket_service
from services.news_fetcher import news_fetcher

logger = logging.getLogger(__name__)


async def _get_orderbook(token_id: str) -> dict:
    book = await polymarket_service.get_orderbook(token_id)
    bids = book.get("bids", [])[:8]
    asks = book.get("asks", [])[:8]
    bid_depth = sum(float(b.get("size", 0)) for b in bids)
    ask_depth = sum(float(a.get("size", 0)) for a in asks)
    best_bid = float(bids[0]["price"]) if bids else 0
    best_ask = float(asks[0]["price"]) if asks else 0
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": round(best_ask - best_bid, 4) if best_ask and best_bid else None,
        "bid_depth_top8": round(bid_depth, 2),
        "ask_depth_top8": round(ask_depth, 2),
        "imbalance": round(bid_depth / ask_depth, 3) if ask_depth > 0 else None,
        "bids": [{"price": b["price"], "size": b["size"]} for b in bids[:5]],
        "asks": [{"price": a["price"], "size": a["size"]} for a in asks[:5]],
    }


async def _get_price_history(token_id: str, interval: str = "6h") -> dict:
    history = await polymarket_service.get_price_history(token_id, interval=interval, fidelity=60)
    if not history:
        return {"prices": [], "count": 0}
    prices = [{"t": h.get("t", ""), "p": round(float(h.get("p", 0)), 4)} for h in history[-30:]]
    first_p = float(history[0].get("p", 0))
    last_p = float(history[-1].get("p", 0))
    change = last_p - first_p
    return {
        "interval": interval,
        "count": len(history),
        "first_price": round(first_p, 4),
        "last_price": round(last_p, 4),
        "change": round(change, 4),
        "change_pct": round(change / first_p * 100, 2) if first_p > 0 else 0,
        "recent_prices": prices,
    }


async def _get_whale_positions(condition_id: str) -> dict:
    from database import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT wt.wallet, ww.username, wt.side, wt.price, wt.size, wt.outcome
            FROM whale_trades wt
            LEFT JOIN whale_watchlist ww ON wt.wallet = ww.wallet
            WHERE wt.condition_id = ?
            ORDER BY wt.whale_timestamp DESC LIMIT 20""",
            (condition_id,),
        )
        rows = await cursor.fetchall()
        trades = [dict(r) for r in rows]
        buy_count = sum(1 for t in trades if t.get("side", "").upper() == "BUY")
        sell_count = sum(1 for t in trades if t.get("side", "").upper() == "SELL")
        buy_volume = sum(float(t.get("size", 0)) for t in trades if t.get("side", "").upper() == "BUY")
        sell_volume = sum(float(t.get("size", 0)) for t in trades if t.get("side", "").upper() == "SELL")
        return {
            "condition_id": condition_id,
            "whale_trade_count": len(trades),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "buy_volume": round(buy_volume, 2),
            "sell_volume": round(sell_volume, 2),
            "consensus": "bullish" if buy_volume > sell_volume * 1.5 else ("bearish" if sell_volume > buy_volume * 1.5 else "mixed"),
            "trades": trades[:10],
        }
    finally:
        await db.close()


async def _search_news(query: str, limit: int = 5) -> dict:
    headlines = await news_fetcher.fetch_headlines(query, limit=limit)
    return {"query": query, "headlines": headlines, "count": len(headlines)}


async def _get_portfolio() -> dict:
    from database import get_db
    balance = await polymarket_service.get_balance()
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM positions WHERE status = 'open' ORDER BY opened_at DESC LIMIT 20"
        )
        rows = await cursor.fetchall()
        positions = [dict(r) for r in rows]
        return {
            "balance": balance,
            "open_positions": len(positions),
            "positions": [{
                "market_title": p.get("market_title", ""),
                "side": p.get("side", ""),
                "entry_price": p.get("entry_price", 0),
                "size": p.get("size", 0),
                "exit_target": p.get("exit_target", 0),
                "stop_loss": p.get("stop_loss", 0),
                "strategy": p.get("strategy", ""),
            } for p in positions],
        }
    finally:
        await db.close()


async def _search_related_markets(query: str) -> dict:
    results = await polymarket_service.search_markets(query=query, limit=5)
    markets = []
    for event in results[:5]:
        if "markets" in event:
            for m in event["markets"][:2]:
                prices = m.get("outcomePrices", "[]")
                if isinstance(prices, str):
                    try:
                        prices = json.loads(prices)
                    except Exception:
                        prices = []
                markets.append({
                    "question": m.get("question", "")[:100],
                    "condition_id": m.get("conditionId", m.get("condition_id", "")),
                    "yes_price": float(prices[0]) if prices else None,
                    "volume": m.get("volume", 0),
                })
        else:
            markets.append({
                "question": event.get("question", event.get("title", ""))[:100],
                "condition_id": event.get("conditionId", event.get("condition_id", "")),
            })
    return {"query": query, "related_markets": markets[:5]}


async def _get_market_info(condition_id: str) -> dict:
    try:
        m = await polymarket_service.get_market(condition_id)
        prices = m.get("outcomePrices", "[]")
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except Exception:
                prices = []
        tokens = m.get("tokens", [])
        return {
            "question": m.get("question", ""),
            "description": (m.get("description", "") or "")[:500],
            "outcomes": m.get("outcomes", []),
            "outcome_prices": prices,
            "volume": m.get("volume", 0),
            "liquidity": m.get("liquidity", 0),
            "end_date": m.get("endDate", ""),
            "active": m.get("active", False),
            "tokens": [{"token_id": t.get("token_id", ""), "outcome": t.get("outcome", "")} for t in tokens],
        }
    except Exception as e:
        return {"error": str(e)}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_orderbook",
            "description": "Get the current orderbook (bids, asks, depth, spread, imbalance) for a market token.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token_id": {"type": "string", "description": "The CLOB token ID for the outcome"},
                },
                "required": ["token_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_history",
            "description": "Get historical price data for a token. Returns recent prices, change, and change percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token_id": {"type": "string", "description": "The CLOB token ID"},
                    "interval": {"type": "string", "enum": ["1h", "6h", "24h", "max"], "description": "Time interval"},
                },
                "required": ["token_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_whale_positions",
            "description": "Check what tracked whale traders have done on a specific market (buy/sell counts, volumes, consensus).",
            "parameters": {
                "type": "object",
                "properties": {
                    "condition_id": {"type": "string", "description": "The market condition ID"},
                },
                "required": ["condition_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search for recent news headlines related to a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "News search query"},
                    "limit": {"type": "integer", "description": "Max headlines to return (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio",
            "description": "Get our current portfolio: balance, open positions, and their details.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_related_markets",
            "description": "Search for related/correlated markets on Polymarket.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for related markets"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_info",
            "description": "Get full metadata for a market: question, description, outcomes, prices, volume, liquidity, tokens.",
            "parameters": {
                "type": "object",
                "properties": {
                    "condition_id": {"type": "string", "description": "The market condition ID"},
                },
                "required": ["condition_id"],
            },
        },
    },
]


TOOL_HANDLERS = {
    "get_orderbook": _get_orderbook,
    "get_price_history": _get_price_history,
    "get_whale_positions": _get_whale_positions,
    "search_news": _search_news,
    "get_portfolio": _get_portfolio,
    "search_related_markets": _search_related_markets,
    "get_market_info": _get_market_info,
}
