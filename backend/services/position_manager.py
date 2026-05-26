"""Shared position tracking and hybrid exit management across all strategies."""

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone, timedelta

from database import get_db, get_config, insert_trade
from services.polymarket import polymarket_service
from services.risk_manager import risk_manager
from services.trading_agent import trading_agent, TradingPlan, OrderPlan
from services.agent_tools import TOOL_SCHEMAS, TOOL_HANDLERS

logger = logging.getLogger(__name__)

HOLD_DURATIONS = {
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "settlement": timedelta(days=365),
}

EXIT_REEVAL_PROMPT = """You are a position management agent for a Polymarket trading bot.
You are reviewing an open position. Analyze the current market data and decide:
1. HOLD - keep the position, no changes
2. EXIT - close the position now (sell)
3. ADJUST - update the exit_target or stop_loss

Consider: current price vs entry, orderbook momentum, time held, whether the original thesis still holds."""


class PositionManager:
    async def open_position(
        self,
        strategy: str,
        token_id: str,
        condition_id: str,
        market_title: str,
        side: str,
        entry_price: float,
        size: float,
        exit_target: float,
        stop_loss: float,
        hold_duration: str,
        agent_plan_id: int | None = None,
    ) -> int:
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            cursor = await db.execute(
                """INSERT INTO positions
                (strategy, token_id, condition_id, market_title, side, entry_price,
                 current_price, size, exit_target, stop_loss, hold_duration, status,
                 pnl, agent_plan_id, opened_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 0.0, ?, ?)""",
                (strategy, token_id, condition_id, market_title, side, entry_price,
                 entry_price, size, exit_target, stop_loss, hold_duration,
                 agent_plan_id, now),
            )
            await db.commit()
            return cursor.lastrowid
        finally:
            await db.close()

    async def close_position(self, position_id: int, exit_price: float, reason: str = ""):
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            cursor = await db.execute("SELECT * FROM positions WHERE id = ?", (position_id,))
            pos = await cursor.fetchone()
            if not pos:
                return
            pos = dict(pos)
            entry = pos["entry_price"]
            size = pos["size"]
            side = pos["side"]
            if side == "buy":
                pnl = (exit_price - entry) * size
            else:
                pnl = (entry - exit_price) * size

            await db.execute(
                """UPDATE positions SET status = 'closed', current_price = ?,
                   pnl = ?, closed_at = ? WHERE id = ?""",
                (exit_price, round(pnl, 4), now, position_id),
            )
            await db.commit()
            logger.info("Closed position %d: pnl=%.2f reason=%s", position_id, pnl, reason)
        finally:
            await db.close()

    async def get_open_positions(self, strategy: str | None = None) -> list[dict]:
        db = await get_db()
        try:
            q = "SELECT * FROM positions WHERE status = 'open'"
            params: list = []
            if strategy:
                q += " AND strategy = ?"
                params.append(strategy)
            q += " ORDER BY opened_at DESC"
            cursor = await db.execute(q, params)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def get_positions(self, status: str | None = None, strategy: str | None = None, limit: int = 50) -> list[dict]:
        db = await get_db()
        try:
            q = "SELECT * FROM positions WHERE 1=1"
            params: list = []
            if status:
                q += " AND status = ?"
                params.append(status)
            if strategy:
                q += " AND strategy = ?"
                params.append(strategy)
            q += " ORDER BY opened_at DESC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(q, params)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def run_mechanical_exits(self, paper_mode: bool = True) -> list[dict]:
        """Check all open positions against stop_loss and exit_target. Returns list of closed positions."""
        positions = await self.get_open_positions()
        closed = []

        for pos in positions:
            token_id = pos["token_id"]
            try:
                book = await polymarket_service.get_orderbook(token_id)
                bids = book.get("bids", [])
                asks = book.get("asks", [])
                if pos["side"] == "buy":
                    current = float(bids[0]["price"]) if bids else pos["current_price"]
                else:
                    current = float(asks[0]["price"]) if asks else pos["current_price"]
            except Exception:
                current = pos["current_price"]

            db = await get_db()
            try:
                await db.execute("UPDATE positions SET current_price = ? WHERE id = ?", (current, pos["id"]))
                await db.commit()
            finally:
                await db.close()

            exit_target = pos["exit_target"]
            stop_loss = pos["stop_loss"]
            reason = ""

            if pos["side"] == "buy":
                if exit_target > 0 and current >= exit_target:
                    reason = f"Take profit: {current:.4f} >= {exit_target:.4f}"
                elif stop_loss > 0 and current <= stop_loss:
                    reason = f"Stop loss: {current:.4f} <= {stop_loss:.4f}"
            else:
                if exit_target > 0 and current <= exit_target:
                    reason = f"Take profit (short): {current:.4f} <= {exit_target:.4f}"
                elif stop_loss > 0 and current >= stop_loss:
                    reason = f"Stop loss (short): {current:.4f} >= {stop_loss:.4f}"

            hold_dur = pos.get("hold_duration", "settlement")
            if hold_dur != "settlement" and pos["opened_at"]:
                try:
                    opened = datetime.fromisoformat(pos["opened_at"])
                    max_dur = HOLD_DURATIONS.get(hold_dur, timedelta(days=365))
                    if datetime.now(timezone.utc) - opened > max_dur:
                        reason = f"Hold duration expired: {hold_dur}"
                except Exception:
                    pass

            if reason:
                if not paper_mode:
                    try:
                        await polymarket_service.place_market_order(
                            token_id=token_id,
                            side="sell" if pos["side"] == "buy" else "buy",
                            size=pos["size"],
                        )
                    except Exception as e:
                        logger.warning("Exit order failed for position %d: %s", pos["id"], e)
                        continue

                await self.close_position(pos["id"], current, reason)
                closed.append({**pos, "exit_price": current, "exit_reason": reason})

        return closed

    async def run_llm_reeval(self, paper_mode: bool = True) -> list[dict]:
        """Re-evaluate open positions using the LLM agent."""
        positions = await self.get_open_positions()
        results = []

        for pos in positions:
            try:
                book_data = await polymarket_service.get_orderbook(pos["token_id"])
                bids = book_data.get("bids", [])[:5]
                asks = book_data.get("asks", [])[:5]
            except Exception:
                bids, asks = [], []

            context = {
                "position": {
                    "market": pos["market_title"],
                    "side": pos["side"],
                    "entry_price": pos["entry_price"],
                    "current_price": pos["current_price"],
                    "size": pos["size"],
                    "exit_target": pos["exit_target"],
                    "stop_loss": pos["stop_loss"],
                    "strategy": pos["strategy"],
                    "opened_at": pos["opened_at"],
                },
                "orderbook": {
                    "best_bid": float(bids[0]["price"]) if bids else None,
                    "best_ask": float(asks[0]["price"]) if asks else None,
                    "bids": bids[:3],
                    "asks": asks[:3],
                },
                "token_id": pos["token_id"],
                "condition_id": pos["condition_id"],
            }

            tools_subset = [t for t in TOOL_SCHEMAS if t["function"]["name"] in ("get_orderbook", "get_price_history")]
            handlers_subset = {k: v for k, v in TOOL_HANDLERS.items() if k in ("get_orderbook", "get_price_history")}

            plan, chain = await trading_agent.run(
                strategy="position_reeval",
                system_prompt=EXIT_REEVAL_PROMPT,
                context=context,
                tools=tools_subset,
                tool_handlers=handlers_subset,
                max_steps=3,
                timeout=15.0,
            )

            action = "hold"
            if plan.orders:
                order = plan.orders[0]
                if order.action == "sell" or order.action == "exit":
                    action = "exit"
                elif order.action == "adjust":
                    action = "adjust"

            if action == "exit":
                current = pos["current_price"]
                if not paper_mode:
                    try:
                        await polymarket_service.place_market_order(
                            token_id=pos["token_id"],
                            side="sell" if pos["side"] == "buy" else "buy",
                            size=pos["size"],
                        )
                    except Exception as e:
                        logger.warning("LLM exit order failed: %s", e)
                        continue
                await self.close_position(pos["id"], current, f"LLM reeval: {plan.reasoning[:100]}")
                results.append({"position_id": pos["id"], "action": "exit", "reasoning": plan.reasoning})

            elif action == "adjust" and plan.orders:
                order = plan.orders[0]
                db = await get_db()
                try:
                    updates = {}
                    if order.exit_target > 0:
                        updates["exit_target"] = order.exit_target
                    if order.stop_loss > 0:
                        updates["stop_loss"] = order.stop_loss
                    if updates:
                        set_clause = ", ".join(f"{k} = ?" for k in updates)
                        await db.execute(
                            f"UPDATE positions SET {set_clause} WHERE id = ?",
                            (*updates.values(), pos["id"]),
                        )
                        await db.commit()
                        results.append({"position_id": pos["id"], "action": "adjust", "updates": updates})
                finally:
                    await db.close()
            else:
                results.append({"position_id": pos["id"], "action": "hold"})

        return results


position_manager = PositionManager()
