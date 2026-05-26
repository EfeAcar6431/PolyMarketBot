"""Strategy A: Whale Conviction

Follow top sports bettors on large, high-conviction bets.
When a whale trade is detected, invoke the LLM trading agent to research
the market and decide whether to follow with aggressive sizing.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from dataclasses import asdict

import httpx

from database import get_db, get_config, log_event, insert_trade
from services.polymarket import polymarket_service
from services.trading_agent import trading_agent, TradingPlan
from services.agent_tools import TOOL_SCHEMAS, TOOL_HANDLERS
from services.risk_manager import risk_manager
from services.position_manager import position_manager

logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

WHALE_SYSTEM_PROMPT = """You are a sports betting analyst on Polymarket. A top-ranked trader just placed a large bet.

Your job:
1. Research the market using the available tools -- check the orderbook for depth and flow, look at price history, check if other whales have positioned similarly.
2. Assess whether following this whale is a good trade. Consider:
   - The whale's track record (PnL, rank)
   - How much price has moved since their entry (slippage)
   - Orderbook depth (can we get in at a good price?)
   - Whether other tracked whales agree (consensus)
   - Any relevant news that might invalidate the trade
3. If you decide to follow, output a trading plan with aggressive sizing.
4. Set hold_duration to "settlement" -- we hold whale conviction bets to resolution.
5. Set appropriate stop_loss (e.g. 30-50% below entry) as a safety net.

IMPORTANT: Be selective. Only follow trades where you have high conviction after research."""


class WhaleConviction:
    def __init__(self):
        self._last_seen: dict[str, int] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Whale Conviction strategy started")

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Whale Conviction strategy stopped")

    async def _loop(self):
        try:
            while self._running:
                config = await get_config()
                enabled = config.get("whale_conviction_enabled", "true").lower() == "true"
                if not enabled:
                    await asyncio.sleep(60)
                    continue
                try:
                    await self.run_cycle(config)
                except Exception as e:
                    logger.exception("Whale conviction cycle error: %s", e)
                interval = int(config.get("scan_interval", 300))
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    async def refresh_watchlist(
        self,
        category: str = "SPORTS",
        time_period: str = "MONTH",
        top_n: int = 20,
    ) -> list[dict]:
        wallets: list[dict] = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{DATA_API}/v1/leaderboard",
                    params={
                        "category": category,
                        "timePeriod": time_period,
                        "orderBy": "PNL",
                        "limit": top_n,
                    },
                )
                resp.raise_for_status()
                wallets = resp.json()
        except Exception as e:
            logger.error("Leaderboard fetch failed: %s", e)
            return []

        min_pnl = 50_000
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            for w in wallets:
                addr = w.get("proxyWallet", "")
                if not addr:
                    continue
                pnl = float(w.get("pnl", 0))
                if pnl < min_pnl:
                    continue
                await db.execute(
                    """INSERT INTO whale_watchlist (wallet, username, category, pnl, added_at, last_checked_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(wallet) DO UPDATE SET
                        username=excluded.username, pnl=excluded.pnl, last_checked_at=excluded.last_checked_at""",
                    (addr, w.get("userName", w.get("pseudonym", "")), category, pnl, now, now),
                )
            await db.commit()
        finally:
            await db.close()
        return wallets

    async def get_watchlist(self, active_only: bool = True) -> list[dict]:
        db = await get_db()
        try:
            q = "SELECT * FROM whale_watchlist"
            if active_only:
                q += " WHERE active = 1"
            q += " ORDER BY pnl DESC"
            cursor = await db.execute(q)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def toggle_whale(self, wallet: str, active: bool):
        db = await get_db()
        try:
            await db.execute("UPDATE whale_watchlist SET active = ? WHERE wallet = ?", (1 if active else 0, wallet))
            await db.commit()
        finally:
            await db.close()

    async def fetch_whale_trades(self, wallet: str, limit: int = 20) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{DATA_API}/trades", params={"user": wallet, "limit": limit})
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("Trade fetch for %s failed: %s", wallet[:10], e)
            return []

    async def detect_new_trades(self, wallet: str, limit: int = 10) -> list[dict]:
        trades = await self.fetch_whale_trades(wallet, limit=limit)
        last_ts = self._last_seen.get(wallet, 0)
        new_trades = [t for t in trades if t.get("timestamp", 0) > last_ts]
        if trades:
            max_ts = max(t.get("timestamp", 0) for t in trades)
            if max_ts > last_ts:
                self._last_seen[wallet] = max_ts
        return new_trades

    async def record_whale_trade(self, wallet: str, trade: dict, followed: bool = False, reason: str = ""):
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                """INSERT OR IGNORE INTO whale_trades
                (wallet, side, price, size, outcome, condition_id, market_title, market_slug,
                 tx_hash, whale_timestamp, followed, follow_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (wallet, trade.get("side", ""), float(trade.get("price", 0)),
                 float(trade.get("size", 0)), trade.get("outcome", ""),
                 trade.get("conditionId", trade.get("condition_id", "")),
                 trade.get("title", ""), trade.get("slug", ""),
                 trade.get("transactionHash", ""), int(trade.get("timestamp", 0)),
                 1 if followed else 0, reason, now),
            )
            await db.commit()
        finally:
            await db.close()

    async def get_recent_whale_trades(self, limit: int = 50) -> list[dict]:
        db = await get_db()
        try:
            cursor = await db.execute(
                """SELECT wt.*, ww.username FROM whale_trades wt
                LEFT JOIN whale_watchlist ww ON wt.wallet = ww.wallet
                ORDER BY wt.whale_timestamp DESC LIMIT ?""", (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def get_whale_stats(self, wallet: str) -> dict:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT COUNT(*) as total, SUM(CASE WHEN followed=1 THEN 1 ELSE 0 END) as followed_count FROM whale_trades WHERE wallet=?",
                (wallet,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else {"total": 0, "followed_count": 0}
        finally:
            await db.close()

    async def run_cycle(self, config: dict):
        paper_mode = config.get("paper_mode", "true").lower() == "true"
        mode_label = "[PAPER] " if paper_mode else ""
        min_trade_size = float(config.get("whale_min_trade_size", 1000))
        sports_only = config.get("whale_sports_only", "true").lower() == "true"
        max_steps = int(config.get("whale_max_agent_steps", 5))

        watchlist = await self.get_watchlist(active_only=True)
        if not watchlist:
            return

        await log_event("info", f"{mode_label}Whale conviction: scanning {len(watchlist)} whales...")

        for whale in watchlist[:15]:
            wallet = whale["wallet"]
            username = whale.get("username", wallet[:10])

            try:
                new_trades = await self.detect_new_trades(wallet, limit=5)
            except Exception as e:
                logger.warning("Failed checking whale %s: %s", username, e)
                continue

            for trade in new_trades:
                size = float(trade.get("size", 0))
                if size < min_trade_size:
                    await self.record_whale_trade(wallet, trade, followed=False,
                                                  reason=f"Too small: ${size:.0f} < ${min_trade_size:.0f}")
                    continue

                side = trade.get("side", "").upper()
                if side == "SELL":
                    await self.record_whale_trade(wallet, trade, followed=False, reason="Whale selling, skip")
                    continue

                condition_id = trade.get("conditionId", trade.get("condition_id", ""))
                token_id = trade.get("asset", "")
                title = trade.get("title", "")

                if not token_id or not condition_id:
                    await self.record_whale_trade(wallet, trade, followed=False, reason="Missing IDs")
                    continue

                context = {
                    "whale": {
                        "username": username,
                        "pnl": whale.get("pnl", 0),
                        "rank": whale.get("rank", "unknown"),
                    },
                    "trade": {
                        "market_title": title,
                        "side": side,
                        "price": float(trade.get("price", 0)),
                        "size": size,
                        "condition_id": condition_id,
                        "token_id": token_id,
                    },
                    "config": {
                        "max_position_size": float(config.get("max_position_size", 50)),
                        "bankroll": float(config.get("max_total_exposure", 500)),
                        "kelly_multiplier": float(config.get("whale_kelly_multiplier", 0.5)),
                    },
                }

                await log_event("info",
                    f"{mode_label}Whale {username} bet ${size:.0f} on '{title[:50]}' — invoking agent...")

                plan, chain = await trading_agent.run(
                    strategy="whale_conviction",
                    system_prompt=WHALE_SYSTEM_PROMPT,
                    context=context,
                    tools=TOOL_SCHEMAS,
                    tool_handlers=TOOL_HANDLERS,
                    max_steps=max_steps,
                    timeout=30.0,
                )

                await self._log_agent_plan("whale_conviction",
                    f"Whale {username} bet ${size:.0f} on {title[:60]}",
                    context, chain, plan)

                if not plan.orders:
                    await self.record_whale_trade(wallet, trade, followed=False,
                                                  reason=f"Agent skip: {plan.reasoning[:100]}")
                    await log_event("info", f"{mode_label}Whale agent skip: {plan.reasoning[:80]}")
                    continue

                for order in plan.orders:
                    if order.action == "skip" or order.size < 1:
                        continue

                    risk = await risk_manager.check_trade(order.side, order.size, order.price)
                    if not risk.approved:
                        await self.record_whale_trade(wallet, trade, followed=False,
                                                      reason=f"Risk rejected: {risk.reason}")
                        await log_event("warning", f"{mode_label}Whale trade rejected: {risk.reason}")
                        await self._update_plan_rejection(plan, risk.reason)
                        continue

                    final_size = risk.adjusted_size
                    use_token = order.token_id or token_id

                    if paper_mode:
                        await log_event("trade",
                            f"[PAPER] Whale conviction {order.side.upper()} ${final_size:.2f} on "
                            f"'{title[:50]}' (whale: {username}, confidence: {plan.confidence:.0%})",
                            {"strategy": "whale_conviction", "whale": username, "paper": True})
                        await insert_trade(
                            market_id=condition_id, market_question=title,
                            token_id=use_token, side=order.side, price=order.price,
                            size=final_size, status="paper",
                            strategy_reason=f"Whale conviction: {username} - {plan.reasoning[:150]}",
                            order_id="PAPER-WHALE",
                        )
                    else:
                        await log_event("trade",
                            f"LIVE whale conviction {order.side.upper()} ${final_size:.2f} on '{title[:50]}'",
                            {"strategy": "whale_conviction", "whale": username})
                        try:
                            result = await polymarket_service.place_limit_order(
                                token_id=use_token, side=order.side,
                                price=order.price, size=final_size,
                            )
                            order_id = result.get("orderID", result.get("id", ""))
                            await insert_trade(
                                market_id=condition_id, market_question=title,
                                token_id=use_token, side=order.side, price=order.price,
                                size=final_size, status="placed",
                                strategy_reason=f"Whale conviction: {username}",
                                order_id=order_id,
                            )
                        except Exception as e:
                            await log_event("error", f"Whale order failed: {e}")
                            continue

                    await position_manager.open_position(
                        strategy="whale_conviction", token_id=use_token,
                        condition_id=condition_id, market_title=title,
                        side=order.side, entry_price=order.price, size=final_size,
                        exit_target=order.exit_target, stop_loss=order.stop_loss,
                        hold_duration=order.hold_duration,
                    )

                    risk_manager.record_trade()
                    await self.record_whale_trade(wallet, trade, followed=True,
                                                  reason=f"Agent approved: {plan.reasoning[:100]}")

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

    async def _update_plan_rejection(self, plan: TradingPlan, reason: str):
        db = await get_db()
        try:
            await db.execute(
                """UPDATE agent_plans SET executed = 0, risk_rejection_reason = ?
                WHERE id = (SELECT MAX(id) FROM agent_plans WHERE strategy = 'whale_conviction')""",
                (reason,),
            )
            await db.commit()
        finally:
            await db.close()


whale_conviction = WhaleConviction()
