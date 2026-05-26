import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass

from database import get_db
from services.polymarket import polymarket_service

logger = logging.getLogger(__name__)

DEFAULT_SPREAD = 0.04
MIN_SPREAD = 0.02
MAX_SPREAD = 0.10
LADDER_LEVELS = 3
LEVEL_SIZE_DECAY = 0.6  # each level is 60% of the previous
INVENTORY_SKEW_FACTOR = 0.5
MAX_IMBALANCE_RATIO = 0.8


@dataclass
class OrderLadder:
    bids: list[dict]
    asks: list[dict]


class MarketMaker:
    def __init__(self):
        self._active_orders: dict[str, list[str]] = {}  # token_id -> [order_ids]

    async def get_inventory(self) -> list[dict]:
        db = await get_db()
        try:
            cursor = await db.execute("SELECT * FROM mm_inventory WHERE active = 1")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def get_all_inventory(self) -> list[dict]:
        db = await get_db()
        try:
            cursor = await db.execute("SELECT * FROM mm_inventory ORDER BY active DESC, updated_at DESC")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def add_market(
        self, token_id: str, condition_id: str, title: str, spread: float = DEFAULT_SPREAD
    ):
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                """INSERT OR REPLACE INTO mm_inventory
                (token_id, condition_id, market_title, target_spread, active, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)""",
                (token_id, condition_id, title, spread, now),
            )
            await db.commit()
        finally:
            await db.close()

    async def remove_market(self, token_id: str):
        await self.cancel_orders(token_id)
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                "UPDATE mm_inventory SET active = 0, updated_at = ? WHERE token_id = ?",
                (now, token_id),
            )
            await db.commit()
        finally:
            await db.close()

    async def update_spread(self, token_id: str, spread: float):
        spread = max(MIN_SPREAD, min(MAX_SPREAD, spread))
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                "UPDATE mm_inventory SET target_spread = ?, updated_at = ? WHERE token_id = ?",
                (spread, now, token_id),
            )
            await db.commit()
        finally:
            await db.close()

    def compute_ladder(
        self,
        midpoint: float,
        target_spread: float,
        base_size: float,
        yes_balance: float = 0.0,
        no_balance: float = 0.0,
    ) -> OrderLadder:
        """Build a price ladder with inventory skew.

        When we hold more YES tokens, we skew bids down (less aggressive buying)
        and asks down (more aggressive selling) to rebalance inventory.
        """
        total = yes_balance + no_balance
        imbalance = 0.0
        if total > 0:
            imbalance = (yes_balance - no_balance) / total

        half_spread = target_spread / 2
        bid_skew = -imbalance * INVENTORY_SKEW_FACTOR * half_spread
        ask_skew = -imbalance * INVENTORY_SKEW_FACTOR * half_spread

        bids = []
        asks = []
        for level in range(LADDER_LEVELS):
            offset = half_spread * (1 + level * 0.5)
            size = base_size * (LEVEL_SIZE_DECAY ** level)
            if size < 1.0:
                continue

            bid_price = round(midpoint - offset + bid_skew, 4)
            ask_price = round(midpoint + offset + ask_skew, 4)

            if 0.01 <= bid_price <= 0.99:
                bids.append({"price": bid_price, "size": round(size, 2), "level": level})
            if 0.01 <= ask_price <= 0.99:
                asks.append({"price": ask_price, "size": round(size, 2), "level": level})

        return OrderLadder(bids=bids, asks=asks)

    async def cancel_orders(self, token_id: str):
        order_ids = self._active_orders.get(token_id, [])
        for oid in order_ids:
            try:
                await polymarket_service.cancel_order(oid)
            except Exception as e:
                logger.warning("Failed to cancel MM order %s: %s", oid, e)
        self._active_orders[token_id] = []

    async def place_ladder(
        self, token_id: str, ladder: OrderLadder, paper_mode: bool = True
    ) -> list[dict]:
        """Place all orders in the ladder. Returns list of placed order summaries."""
        placed = []

        for bid in ladder.bids:
            if paper_mode:
                placed.append({"side": "buy", "price": bid["price"], "size": bid["size"], "status": "paper"})
            else:
                try:
                    result = await polymarket_service.place_limit_order(
                        token_id=token_id,
                        side="buy",
                        price=bid["price"],
                        size=bid["size"],
                    )
                    oid = result.get("orderID", result.get("id", ""))
                    if token_id not in self._active_orders:
                        self._active_orders[token_id] = []
                    self._active_orders[token_id].append(oid)
                    placed.append({"side": "buy", "price": bid["price"], "size": bid["size"], "status": "placed", "order_id": oid})
                except Exception as e:
                    placed.append({"side": "buy", "price": bid["price"], "size": bid["size"], "status": f"failed: {e}"})

        for ask in ladder.asks:
            if paper_mode:
                placed.append({"side": "sell", "price": ask["price"], "size": ask["size"], "status": "paper"})
            else:
                try:
                    result = await polymarket_service.place_limit_order(
                        token_id=token_id,
                        side="sell",
                        price=ask["price"],
                        size=ask["size"],
                    )
                    oid = result.get("orderID", result.get("id", ""))
                    if token_id not in self._active_orders:
                        self._active_orders[token_id] = []
                    self._active_orders[token_id].append(oid)
                    placed.append({"side": "sell", "price": ask["price"], "size": ask["size"], "status": "placed", "order_id": oid})
                except Exception as e:
                    placed.append({"side": "sell", "price": ask["price"], "size": ask["size"], "status": f"failed: {e}"})

        return placed

    def compute_reward_score(self, spread: float, size: float, max_spread: float = 0.10) -> float:
        """Polymarket quadratic reward formula: S = ((maxSpread - spread) / maxSpread)^2 * size"""
        if spread >= max_spread or spread <= 0:
            return 0.0
        ratio = (max_spread - spread) / max_spread
        return ratio * ratio * size

    async def run_cycle(self, config: dict) -> list[dict]:
        """Run one market-making cycle: cancel stale orders, compute new ladders, place them."""
        paper_mode = config.get("paper_mode", "true").lower() == "true"
        base_size = float(config.get("mm_order_size", 20.0))
        inventory = await self.get_inventory()
        results = []

        for item in inventory:
            token_id = item["token_id"]
            target_spread = item.get("target_spread", DEFAULT_SPREAD)

            try:
                midpoint = await polymarket_service.get_midpoint(token_id)
            except Exception as e:
                logger.warning("MM midpoint fetch failed for %s: %s", token_id[:10], e)
                results.append({"token_id": token_id, "error": str(e)})
                continue

            await self.cancel_orders(token_id)

            ladder = self.compute_ladder(
                midpoint=midpoint,
                target_spread=target_spread,
                base_size=base_size,
                yes_balance=item.get("yes_balance", 0),
                no_balance=item.get("no_balance", 0),
            )

            placed = await self.place_ladder(token_id, ladder, paper_mode=paper_mode)
            reward = sum(
                self.compute_reward_score(target_spread, o["size"])
                for o in placed
            )

            results.append({
                "token_id": token_id,
                "title": item.get("market_title", ""),
                "midpoint": midpoint,
                "spread": target_spread,
                "orders_placed": len(placed),
                "reward_score": round(reward, 2),
                "paper": paper_mode,
            })

        return results


market_maker = MarketMaker()
