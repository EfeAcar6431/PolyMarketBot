import asyncio
import logging
from datetime import datetime, timezone

import httpx

from database import get_db, log_event
from services.llm_analyzer import llm_analyzer
from services.edge_validator import edge_validator
from services.risk_manager import risk_manager
from services.polymarket import polymarket_service

logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

MIN_PNL = 50_000
MIN_TRADES_FOR_FOLLOW = 5
MAX_SLIPPAGE = 0.03
MIN_WHALE_TRADE_SIZE = 500


class WhaleTracker:
    def __init__(self):
        self._last_seen: dict[str, int] = {}  # wallet -> latest whale_timestamp seen

    async def refresh_watchlist(
        self,
        category: str = "OVERALL",
        time_period: str = "MONTH",
        top_n: int = 20,
    ) -> list[dict]:
        """Pull leaderboard and upsert into whale_watchlist."""
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

        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            for w in wallets:
                addr = w.get("proxyWallet", "")
                if not addr:
                    continue
                pnl = float(w.get("pnl", 0))
                if pnl < MIN_PNL:
                    continue
                await db.execute(
                    """INSERT INTO whale_watchlist (wallet, username, category, pnl, added_at, last_checked_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(wallet) DO UPDATE SET
                        username=excluded.username,
                        pnl=excluded.pnl,
                        last_checked_at=excluded.last_checked_at""",
                    (
                        addr,
                        w.get("userName", w.get("pseudonym", "")),
                        category,
                        pnl,
                        now,
                        now,
                    ),
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

    async def fetch_whale_trades(self, wallet: str, limit: int = 20) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{DATA_API}/trades",
                    params={"user": wallet, "limit": limit},
                )
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
                (wallet, side, price, size, outcome, condition_id, market_title, market_slug, tx_hash, whale_timestamp, followed, follow_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    wallet,
                    trade.get("side", ""),
                    float(trade.get("price", 0)),
                    float(trade.get("size", 0)),
                    trade.get("outcome", ""),
                    trade.get("conditionId", trade.get("condition_id", "")),
                    trade.get("title", ""),
                    trade.get("slug", ""),
                    trade.get("transactionHash", ""),
                    int(trade.get("timestamp", 0)),
                    1 if followed else 0,
                    reason,
                    now,
                ),
            )
            await db.commit()
        finally:
            await db.close()

    async def evaluate_whale_signal(
        self,
        trade: dict,
        whale_username: str,
        config: dict,
    ) -> dict:
        """Evaluate whether we should follow a whale trade. Returns decision dict."""
        size = float(trade.get("size", 0))
        if size < MIN_WHALE_TRADE_SIZE:
            return {"follow": False, "reason": f"Trade too small (${size:.0f} < ${MIN_WHALE_TRADE_SIZE})"}

        side = trade.get("side", "").upper()
        if side == "SELL":
            return {"follow": False, "reason": "Whale is selling — we only follow buys for now"}

        title = trade.get("title", "")
        whale_price = float(trade.get("price", 0))
        condition_id = trade.get("conditionId", trade.get("condition_id", ""))
        token_id = trade.get("asset", "")

        if not token_id or not condition_id:
            return {"follow": False, "reason": "Missing token/condition ID"}

        try:
            book = await polymarket_service.get_orderbook(token_id)
            best_ask = None
            asks = book.get("asks", [])
            if asks:
                best_ask = float(asks[0].get("price", 0))
        except Exception:
            best_ask = None

        if best_ask is not None:
            slippage = (best_ask - whale_price) / whale_price if whale_price > 0 else 0
            if slippage > MAX_SLIPPAGE:
                return {
                    "follow": False,
                    "reason": f"Price moved too much since whale entry ({slippage*100:.1f}% slippage > {MAX_SLIPPAGE*100:.0f}% max)",
                }
            current_price = best_ask
        else:
            current_price = whale_price

        try:
            analysis = await llm_analyzer.analyze_market(
                question=title,
                current_price=current_price,
            )
            llm_agrees = analysis.get("edge", 0) > 0 and analysis.get("confidence", 0) >= 0.3
        except Exception:
            llm_agrees = True  # fail-open

        if not llm_agrees:
            return {
                "follow": False,
                "reason": f"LLM disagrees with whale (LLM edge: {analysis.get('edge', 0)*100:.1f}%)",
                "llm_analysis": analysis,
            }

        max_pos = float(config.get("max_position_size", 50.0))
        bankroll = float(config.get("max_total_exposure", 500.0))
        llm_prob = analysis.get("estimated_probability", current_price)
        confidence = analysis.get("confidence", 0.5)
        category = trade.get("eventSlug", "").split("-")[0] if trade.get("eventSlug") else ""
        fee = edge_validator.get_fee_rate(category)
        bet_size, kelly = edge_validator.quarter_kelly(llm_prob, current_price, confidence, bankroll, fee)
        bet_size = min(max(bet_size, 1.0), max_pos)

        return {
            "follow": True,
            "reason": f"Whale {whale_username} + LLM agree (edge: {analysis.get('edge',0)*100:.1f}%)",
            "side": "buy",
            "price": current_price,
            "size": bet_size,
            "token_id": token_id,
            "condition_id": condition_id,
            "title": title,
            "kelly": kelly,
            "llm_analysis": analysis,
        }

    async def get_recent_whale_trades(self, limit: int = 50) -> list[dict]:
        db = await get_db()
        try:
            cursor = await db.execute(
                """SELECT wt.*, ww.username FROM whale_trades wt
                LEFT JOIN whale_watchlist ww ON wt.wallet = ww.wallet
                ORDER BY wt.whale_timestamp DESC LIMIT ?""",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def toggle_whale(self, wallet: str, active: bool):
        db = await get_db()
        try:
            await db.execute(
                "UPDATE whale_watchlist SET active = ? WHERE wallet = ?",
                (1 if active else 0, wallet),
            )
            await db.commit()
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


whale_tracker = WhaleTracker()
