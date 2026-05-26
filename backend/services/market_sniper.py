"""Strategy C: New Market Sniper

Detect newly created markets in real-time via WebSocket and Gamma API polling.
Invoke the LLM agent to assess if the initial price is mispriced, and snipe
before smart money arrives.
"""

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

import httpx
import websockets

from database import get_db, get_config, log_event, insert_trade
from services.polymarket import polymarket_service
from services.trading_agent import trading_agent, TradingPlan
from services.agent_tools import TOOL_SCHEMAS, TOOL_HANDLERS
from services.risk_manager import risk_manager
from services.position_manager import position_manager

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

SNIPER_SYSTEM_PROMPT = """You are a new-market sniper on Polymarket. A brand-new prediction market was just created and may be mispriced.

Key facts:
- New markets often launch at naive 50/50 pricing or with minimal thought to true probability
- You have SECONDS before smart money reprices it
- Speed matters -- be decisive

Your job:
1. Assess the true probability of the question. Use search_news and search_related_markets if helpful, but be FAST.
2. Compare your assessed probability to the initial market price.
3. If mispriced by more than the min_edge threshold, output a trading plan.
4. Use limit orders at slightly better than current price.
5. Set stop_loss at ~15-20% worse than entry (new markets can be volatile).
6. Set hold_duration to "2h" or "4h" -- wait for the market to reprice toward your assessed value.

If the market is fairly priced or you can't assess it confidently, output empty orders."""


class MarketSniper:
    def __init__(self):
        self._running = False
        self._ws_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._seen_markets: set[str] = set()
        self._processing: set[str] = set()

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            return
        self._running = True

        await self._seed_seen_markets()

        self._ws_task = asyncio.create_task(self._ws_listener())
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Market Sniper strategy started (WS + polling)")

    async def stop(self):
        self._running = False
        for task in (self._ws_task, self._poll_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._ws_task = None
        self._poll_task = None
        logger.info("Market Sniper strategy stopped")

    async def _seed_seen_markets(self):
        """Seed the seen set so we don't snipe existing markets on startup."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{GAMMA_API}/events",
                    params={"order": "startDate", "ascending": "false", "active": "true",
                            "closed": "false", "limit": 50},
                )
                resp.raise_for_status()
                events = resp.json()
                for e in events:
                    for m in e.get("markets", []):
                        cid = m.get("conditionId", m.get("condition_id", ""))
                        if cid:
                            self._seen_markets.add(cid)
                logger.info("Sniper seeded with %d known markets", len(self._seen_markets))
        except Exception as e:
            logger.warning("Failed to seed sniper markets: %s", e)

    async def _ws_listener(self):
        """Primary detection: WebSocket new_market events."""
        while self._running:
            try:
                async with websockets.connect(WS_URL, ping_interval=10, ping_timeout=5) as ws:
                    sub = json.dumps({
                        "assets_ids": [],
                        "type": "market",
                        "custom_feature_enabled": True,
                    })
                    await ws.send(sub)
                    logger.info("Sniper WebSocket connected")

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw_msg) if isinstance(raw_msg, str) else json.loads(raw_msg.decode())
                        except Exception:
                            continue

                        if isinstance(msg, list):
                            for item in msg:
                                await self._handle_ws_event(item)
                        else:
                            await self._handle_ws_event(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Sniper WS error: %s — reconnecting in 10s", e)
                await asyncio.sleep(10)

    async def _handle_ws_event(self, msg: dict):
        event_type = msg.get("event_type", "")
        if event_type != "new_market":
            return

        condition_id = msg.get("condition_id", "")
        if not condition_id or condition_id in self._seen_markets:
            return

        self._seen_markets.add(condition_id)
        token_ids = msg.get("clob_token_ids", [])
        tags = msg.get("tags", [])

        logger.info("Sniper WS: new market detected: %s (tags: %s)", condition_id[:20], tags)
        asyncio.create_task(self._evaluate_new_market(condition_id, token_ids, source="websocket"))

    async def _poll_loop(self):
        """Fallback: poll Gamma API for new events."""
        try:
            while self._running:
                config = await get_config()
                enabled = config.get("sniper_enabled", "false").lower() == "true"
                if not enabled:
                    await asyncio.sleep(30)
                    continue

                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get(
                            f"{GAMMA_API}/events",
                            params={"order": "startDate", "ascending": "false",
                                    "active": "true", "closed": "false", "limit": 10},
                        )
                        resp.raise_for_status()
                        events = resp.json()

                    for event in events:
                        for m in event.get("markets", []):
                            cid = m.get("conditionId", m.get("condition_id", ""))
                            if not cid or cid in self._seen_markets:
                                continue
                            self._seen_markets.add(cid)
                            tokens = m.get("tokens", [])
                            token_ids = [t.get("token_id", "") for t in tokens if t.get("token_id")]
                            logger.info("Sniper poll: new market detected: %s", m.get("question", "")[:50])
                            asyncio.create_task(self._evaluate_new_market(cid, token_ids, source="polling"))

                except Exception as e:
                    logger.warning("Sniper poll error: %s", e)

                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    async def _evaluate_new_market(self, condition_id: str, token_ids: list[str], source: str = ""):
        if condition_id in self._processing:
            return
        self._processing.add(condition_id)

        config = await get_config()
        enabled = config.get("sniper_enabled", "false").lower() == "true"
        if not enabled:
            self._processing.discard(condition_id)
            return

        paper_mode = config.get("paper_mode", "true").lower() == "true"
        mode_label = "[PAPER] " if paper_mode else ""
        min_edge = float(config.get("sniper_min_edge", 0.10))
        max_bet = float(config.get("sniper_max_bet", 50))
        llm_timeout = float(config.get("sniper_llm_timeout", 8))
        max_steps = int(config.get("sniper_max_agent_steps", 3))

        try:
            market_data = await self._fetch_market_data(condition_id)
        except Exception as e:
            logger.warning("Sniper: failed to fetch market %s: %s", condition_id[:15], e)
            self._processing.discard(condition_id)
            return

        question = market_data.get("question", "")
        prices = market_data.get("outcomePrices", [])
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except Exception:
                prices = []

        initial_price = float(prices[0]) if prices else 0.5
        tokens = market_data.get("tokens", [])
        yes_token_id = ""
        for t in tokens:
            if t.get("outcome", "").lower() == "yes":
                yes_token_id = t.get("token_id", "")
                break
        if not yes_token_id and token_ids:
            yes_token_id = token_ids[0]
        if not yes_token_id and tokens:
            yes_token_id = tokens[0].get("token_id", "")

        context = {
            "market": {
                "question": question,
                "description": (market_data.get("description", "") or "")[:400],
                "condition_id": condition_id,
                "token_id": yes_token_id,
                "initial_price": initial_price,
                "outcomes": market_data.get("outcomes", []),
                "liquidity": market_data.get("liquidity", 0),
                "tags": market_data.get("tags", []),
            },
            "config": {
                "min_edge": min_edge,
                "max_bet": max_bet,
            },
            "source": source,
        }

        await log_event("info",
            f"{mode_label}Sniper: new market '{question[:50]}' (price: {initial_price:.2f}) — invoking agent...")

        tools_subset = [t for t in TOOL_SCHEMAS
                       if t["function"]["name"] in ("search_news", "search_related_markets", "get_orderbook")]
        handlers_subset = {k: v for k, v in TOOL_HANDLERS.items()
                          if k in ("search_news", "search_related_markets", "get_orderbook")}

        plan, chain = await trading_agent.run(
            strategy="new_market_sniper",
            system_prompt=SNIPER_SYSTEM_PROMPT,
            context=context,
            tools=tools_subset,
            tool_handlers=handlers_subset,
            max_steps=max_steps,
            timeout=llm_timeout,
        )

        await self._log_agent_plan("new_market_sniper",
            f"New market: {question[:60]} @ {initial_price:.2f}",
            context, chain, plan)

        action = "skip"
        bet_size = 0.0
        bet_side = ""

        if plan.orders:
            order = plan.orders[0]
            if order.action != "skip" and order.size >= 1:
                risk = await risk_manager.check_trade(order.side, min(order.size, max_bet), order.price)
                if risk.approved:
                    action = "bet"
                    bet_size = risk.adjusted_size
                    bet_side = order.side
                    use_token = order.token_id or yes_token_id

                    if paper_mode:
                        await log_event("trade",
                            f"[PAPER] Sniper {bet_side.upper()} ${bet_size:.2f} on '{question[:40]}' "
                            f"(initial: {initial_price:.2f}, confidence: {plan.confidence:.0%})",
                            {"strategy": "new_market_sniper", "paper": True})
                        await insert_trade(
                            market_id=condition_id, market_question=question,
                            token_id=use_token, side=bet_side, price=order.price,
                            size=bet_size, status="paper",
                            strategy_reason=f"Sniper: {plan.reasoning[:150]}",
                            order_id="PAPER-SNIPER",
                        )
                    else:
                        await log_event("trade",
                            f"LIVE sniper {bet_side.upper()} ${bet_size:.2f} on '{question[:40]}'",
                            {"strategy": "new_market_sniper"})
                        try:
                            result = await polymarket_service.place_limit_order(
                                token_id=use_token, side=bet_side,
                                price=order.price, size=bet_size,
                            )
                            oid = result.get("orderID", result.get("id", ""))
                            await insert_trade(
                                market_id=condition_id, market_question=question,
                                token_id=use_token, side=bet_side, price=order.price,
                                size=bet_size, status="placed",
                                strategy_reason=f"Sniper: new market",
                                order_id=oid,
                            )
                        except Exception as e:
                            await log_event("error", f"Sniper order failed: {e}")
                            action = "order_failed"

                    if action == "bet":
                        await position_manager.open_position(
                            strategy="new_market_sniper", token_id=use_token,
                            condition_id=condition_id, market_title=question,
                            side=bet_side, entry_price=order.price, size=bet_size,
                            exit_target=order.exit_target, stop_loss=order.stop_loss,
                            hold_duration=order.hold_duration or "2h",
                        )
                        risk_manager.record_trade()
                else:
                    action = f"risk_rejected: {risk.reason}"
        else:
            await log_event("info", f"{mode_label}Sniper agent skip: {plan.reasoning[:80]}")

        await self._record_detection(
            condition_id=condition_id, market_title=question, token_id=yes_token_id,
            initial_price=initial_price, agent_assessment=plan.reasoning,
            action=action, bet_size=bet_size, bet_side=bet_side,
        )

        asyncio.create_task(self._check_price_later(condition_id, yes_token_id, delay=300))
        self._processing.discard(condition_id)

    async def _fetch_market_data(self, condition_id: str) -> dict:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(f"{GAMMA_API}/markets/{condition_id}")
            resp.raise_for_status()
            return resp.json()

    async def _record_detection(self, condition_id: str, market_title: str, token_id: str,
                                 initial_price: float, agent_assessment: str, action: str,
                                 bet_size: float, bet_side: str):
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                """INSERT INTO sniper_detections
                (condition_id, market_title, token_id, detected_at, initial_price,
                 agent_assessment, action, bet_size, bet_side)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (condition_id, market_title, token_id, now, initial_price,
                 agent_assessment[:500], action, bet_size, bet_side),
            )
            await db.commit()
        finally:
            await db.close()

    async def _check_price_later(self, condition_id: str, token_id: str, delay: int = 300):
        """After delay seconds, record what the price moved to."""
        await asyncio.sleep(delay)
        try:
            if token_id:
                book = await polymarket_service.get_orderbook(token_id)
                asks = book.get("asks", [])
                price_later = float(asks[0]["price"]) if asks else None
            else:
                price_later = None

            if price_later is not None:
                db = await get_db()
                try:
                    await db.execute(
                        "UPDATE sniper_detections SET price_5min_later = ? WHERE condition_id = ? AND price_5min_later IS NULL",
                        (price_later, condition_id),
                    )
                    await db.commit()
                finally:
                    await db.close()
        except Exception as e:
            logger.debug("Sniper price check failed for %s: %s", condition_id[:15], e)

    async def get_detections(self, limit: int = 50) -> list[dict]:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM sniper_detections ORDER BY detected_at DESC LIMIT ?", (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def _log_agent_plan(self, strategy: str, trigger: str, context: dict, chain: list, plan: TradingPlan):
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                """INSERT INTO agent_plans
                (strategy, trigger_summary, context_json, reasoning_chain, plan_json, executed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (strategy, trigger, json.dumps(context, default=str),
                 json.dumps(chain, default=str),
                 json.dumps({"reasoning": plan.reasoning, "confidence": plan.confidence,
                             "orders": [asdict(o) for o in plan.orders]}, default=str),
                 1 if plan.orders else 0, now),
            )
            await db.commit()
        finally:
            await db.close()


market_sniper = MarketSniper()
