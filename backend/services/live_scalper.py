"""Strategy B: Live Scalper

Two-layer design:
  Layer 1 - Fast statistical pre-filter (runs every 15-30s, no LLM)
  Layer 2 - LLM agent invocation when signals cross threshold
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from database import get_db, get_config, log_event, insert_trade
from services.polymarket import polymarket_service
from services.trading_agent import trading_agent, TradingPlan
from services.agent_tools import TOOL_SCHEMAS, TOOL_HANDLERS
from services.risk_manager import risk_manager
from services.position_manager import position_manager

logger = logging.getLogger(__name__)

SCALPER_SYSTEM_PROMPT = """You are a quantitative market scalper on Polymarket. Statistical signals have flagged this market for potential short-term trading opportunity.

You will receive:
- Recent price snapshots (momentum data)
- Orderbook summary (depth, imbalance, spread)
- Signal scores (momentum, imbalance, volume spike, spread)
- Our current open positions

Your job:
1. Analyze the data using available tools if needed (check orderbook depth, price history).
2. Determine if this is a MOMENTUM play (price trending, ride it) or MEAN-REVERSION (overextended, fade it).
3. If you decide to trade, output a plan with:
   - Small position size (the config will tell you the max)
   - Tight profit target: 3-5% above entry for buys
   - Tight stop loss: 2-3% below entry for buys
   - Short hold_duration: "30m", "1h", or "2h"
4. If signals are ambiguous or risk/reward is poor, output an empty orders list.

Be precise with entry prices. Use limit orders at or slightly better than current price."""


@dataclass
class MarketSnapshot:
    token_id: str
    condition_id: str
    question: str
    price: float
    bid_depth: float
    ask_depth: float
    volume_24h: float
    spread: float
    timestamp: float


class LiveScalper:
    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._snapshots: dict[str, list[MarketSnapshot]] = {}
        self._cycle_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Live Scalper strategy started")

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Live Scalper strategy stopped")

    async def _loop(self):
        try:
            while self._running:
                config = await get_config()
                enabled = config.get("scalper_enabled", "false").lower() == "true"
                if not enabled:
                    await asyncio.sleep(30)
                    continue
                try:
                    await self.run_cycle(config)
                except Exception as e:
                    logger.exception("Scalper cycle error: %s", e)
                interval = int(config.get("scalper_interval", 30))
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    def _compute_signals(self, token_id: str) -> dict:
        snapshots = self._snapshots.get(token_id, [])
        if len(snapshots) < 3:
            return {"momentum": 0, "imbalance": 0, "volume_spike": 0, "spread_score": 0, "composite": 0}

        recent = snapshots[-5:] if len(snapshots) >= 5 else snapshots
        prices = [s.price for s in recent]

        momentum = 0.0
        if len(prices) >= 2 and prices[0] > 0:
            momentum = (prices[-1] - prices[0]) / prices[0]

        latest = snapshots[-1]
        imbalance = 0.0
        if latest.ask_depth > 0:
            ratio = latest.bid_depth / latest.ask_depth
            imbalance = (ratio - 1.0) / 2.0
            imbalance = max(-1.0, min(1.0, imbalance))

        volume_spike = 0.0
        if len(snapshots) >= 5:
            avg_vol = sum(s.volume_24h for s in snapshots[-5:]) / 5
            if avg_vol > 0:
                volume_spike = (latest.volume_24h - avg_vol) / avg_vol
                volume_spike = max(-1.0, min(1.0, volume_spike))

        spread_score = 0.0
        if latest.spread > 0:
            spread_score = min(1.0, latest.spread / 0.1)

        composite = (momentum * 0.35 + imbalance * 0.35 + volume_spike * 0.2 + spread_score * 0.1)
        composite = max(-1.0, min(1.0, composite))

        return {
            "momentum": round(momentum, 4),
            "imbalance": round(imbalance, 4),
            "volume_spike": round(volume_spike, 4),
            "spread_score": round(spread_score, 4),
            "composite": round(composite, 4),
        }

    def get_all_signals(self) -> list[dict]:
        results = []
        for token_id, snaps in self._snapshots.items():
            if not snaps:
                continue
            signals = self._compute_signals(token_id)
            latest = snaps[-1]
            results.append({
                "token_id": token_id,
                "question": latest.question,
                "price": latest.price,
                "spread": latest.spread,
                **signals,
            })
        results.sort(key=lambda x: abs(x["composite"]), reverse=True)
        return results

    async def run_cycle(self, config: dict):
        self._cycle_count += 1
        paper_mode = config.get("paper_mode", "true").lower() == "true"
        mode_label = "[PAPER] " if paper_mode else ""
        signal_threshold = float(config.get("scalper_signal_threshold", 0.3))
        max_positions = int(config.get("scalper_max_positions", 5))
        position_size = float(config.get("scalper_position_size", 15))

        try:
            events = await polymarket_service.search_markets(sort_by="volume24hr", limit=10)
        except Exception as e:
            logger.warning("Scalper market fetch failed: %s", e)
            return

        markets = []
        for event in events:
            if "markets" in event:
                for m in event["markets"]:
                    markets.append(m)
            else:
                markets.append(event)

        now = time.time()
        for m in markets[:15]:
            tokens = m.get("tokens", [])
            if not tokens:
                continue
            yes_token = None
            for t in tokens:
                if t.get("outcome", "").lower() == "yes":
                    yes_token = t
                    break
            if not yes_token:
                yes_token = tokens[0] if tokens else None
            if not yes_token:
                continue

            token_id = yes_token.get("token_id", "")
            if not token_id:
                continue

            price = float(yes_token.get("price", 0.5))
            condition_id = m.get("conditionId", m.get("condition_id", m.get("id", "")))
            question = m.get("question", m.get("title", ""))

            try:
                book = await polymarket_service.get_orderbook(token_id)
                bids = book.get("bids", [])[:5]
                asks = book.get("asks", [])[:5]
                bid_depth = sum(float(b.get("size", 0)) for b in bids)
                ask_depth = sum(float(a.get("size", 0)) for a in asks)
                best_bid = float(bids[0]["price"]) if bids else price
                best_ask = float(asks[0]["price"]) if asks else price
                spread = best_ask - best_bid
            except Exception:
                bid_depth, ask_depth, spread = 0, 0, 0

            vol_24h = float(m.get("volume24hr", 0) or 0)

            snap = MarketSnapshot(
                token_id=token_id, condition_id=condition_id, question=question,
                price=price, bid_depth=bid_depth, ask_depth=ask_depth,
                volume_24h=vol_24h, spread=spread, timestamp=now,
            )

            if token_id not in self._snapshots:
                self._snapshots[token_id] = []
            self._snapshots[token_id].append(snap)
            if len(self._snapshots[token_id]) > 60:
                self._snapshots[token_id] = self._snapshots[token_id][-60:]

            await self._save_snapshot(snap)

        await position_manager.run_mechanical_exits(paper_mode)

        if self._cycle_count % 5 == 0:
            open_positions = await position_manager.get_open_positions(strategy="live_scalper")
            if open_positions:
                await log_event("info", f"{mode_label}Scalper: re-evaluating {len(open_positions)} open positions")
                await position_manager.run_llm_reeval(paper_mode)

        current_open = await position_manager.get_open_positions(strategy="live_scalper")
        if len(current_open) >= max_positions:
            return

        for token_id, snaps in self._snapshots.items():
            if len(snaps) < 3:
                continue

            signals = self._compute_signals(token_id)
            if abs(signals["composite"]) < signal_threshold:
                continue

            already_open = any(p["token_id"] == token_id for p in current_open)
            if already_open:
                continue

            latest = snaps[-1]
            recent_prices = [{"price": s.price, "time": s.timestamp} for s in snaps[-20:]]

            context = {
                "market": {
                    "question": latest.question,
                    "condition_id": latest.condition_id,
                    "token_id": token_id,
                    "current_price": latest.price,
                    "volume_24h": latest.volume_24h,
                },
                "signals": signals,
                "recent_snapshots": recent_prices[-15:],
                "orderbook": {
                    "bid_depth": latest.bid_depth,
                    "ask_depth": latest.ask_depth,
                    "spread": latest.spread,
                },
                "config": {
                    "position_size": position_size,
                    "target_pct": float(config.get("scalper_target_pct", 0.04)),
                    "stop_pct": float(config.get("scalper_stop_pct", 0.03)),
                },
            }

            await log_event("info",
                f"{mode_label}Scalper signal on '{latest.question[:40]}' "
                f"(composite: {signals['composite']:.3f}) — invoking agent...")

            tools_subset = [t for t in TOOL_SCHEMAS
                           if t["function"]["name"] in ("get_orderbook", "get_price_history", "get_portfolio")]
            handlers_subset = {k: v for k, v in TOOL_HANDLERS.items()
                              if k in ("get_orderbook", "get_price_history", "get_portfolio")}

            plan, chain = await trading_agent.run(
                strategy="live_scalper",
                system_prompt=SCALPER_SYSTEM_PROMPT,
                context=context,
                tools=tools_subset,
                tool_handlers=handlers_subset,
                max_steps=3,
                timeout=15.0,
            )

            await self._log_agent_plan("live_scalper",
                f"Signal {signals['composite']:.3f} on {latest.question[:60]}",
                context, chain, plan)

            if not plan.orders:
                await log_event("info", f"{mode_label}Scalper agent skip: {plan.reasoning[:80]}")
                continue

            for order in plan.orders:
                if order.action == "skip" or order.size < 1:
                    continue

                order.size = min(order.size, position_size)

                risk = await risk_manager.check_trade(order.side, order.size, order.price)
                if not risk.approved:
                    await log_event("warning", f"{mode_label}Scalper trade rejected: {risk.reason}")
                    continue

                final_size = risk.adjusted_size
                use_token = order.token_id or token_id

                if paper_mode:
                    await log_event("trade",
                        f"[PAPER] Scalper {order.side.upper()} ${final_size:.2f} on "
                        f"'{latest.question[:40]}' (target: {order.exit_target:.4f}, stop: {order.stop_loss:.4f})",
                        {"strategy": "live_scalper", "paper": True})
                    await insert_trade(
                        market_id=latest.condition_id, market_question=latest.question,
                        token_id=use_token, side=order.side, price=order.price,
                        size=final_size, status="paper",
                        strategy_reason=f"Scalper: {plan.reasoning[:150]}",
                        order_id="PAPER-SCALPER",
                    )
                else:
                    await log_event("trade",
                        f"LIVE scalper {order.side.upper()} ${final_size:.2f} on '{latest.question[:40]}'",
                        {"strategy": "live_scalper"})
                    try:
                        result = await polymarket_service.place_limit_order(
                            token_id=use_token, side=order.side,
                            price=order.price, size=final_size,
                        )
                        order_id_str = result.get("orderID", result.get("id", ""))
                        await insert_trade(
                            market_id=latest.condition_id, market_question=latest.question,
                            token_id=use_token, side=order.side, price=order.price,
                            size=final_size, status="placed",
                            strategy_reason=f"Scalper: {plan.reasoning[:100]}",
                            order_id=order_id_str,
                        )
                    except Exception as e:
                        await log_event("error", f"Scalper order failed: {e}")
                        continue

                await position_manager.open_position(
                    strategy="live_scalper", token_id=use_token,
                    condition_id=latest.condition_id, market_title=latest.question,
                    side=order.side, entry_price=order.price, size=final_size,
                    exit_target=order.exit_target, stop_loss=order.stop_loss,
                    hold_duration=order.hold_duration or "1h",
                )
                risk_manager.record_trade()

            current_open = await position_manager.get_open_positions(strategy="live_scalper")
            if len(current_open) >= max_positions:
                break

    async def _save_snapshot(self, snap: MarketSnapshot):
        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO scalper_snapshots
                (token_id, price, bid_depth, ask_depth, volume_24h, spread, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (snap.token_id, snap.price, snap.bid_depth, snap.ask_depth,
                 snap.volume_24h, snap.spread, datetime.now(timezone.utc).isoformat()),
            )
            await db.execute(
                "DELETE FROM scalper_snapshots WHERE id NOT IN (SELECT id FROM scalper_snapshots ORDER BY id DESC LIMIT 5000)"
            )
            await db.commit()
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


live_scalper = LiveScalper()
