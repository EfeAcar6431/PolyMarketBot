import asyncio
import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field

from database import get_db
from services.polymarket import polymarket_service
from services.llm_analyzer import llm_analyzer
from services.edge_validator import edge_validator
from services.risk_manager import risk_manager

logger = logging.getLogger(__name__)

MOVE_THRESHOLD_PCT = 0.08
WINDOW_SECONDS = 1800  # 30 minutes
MIN_VOLUME_24H = 5000
COOLDOWN_PER_MARKET = 3600  # 1 hour between alerts on same market


@dataclass
class PriceSnapshot:
    price: float
    timestamp: float


@dataclass
class SentimentAlert:
    condition_id: str
    token_id: str
    title: str
    price_before: float
    price_after: float
    change_pct: float
    window_seconds: int


class SentimentMonitor:
    def __init__(self):
        self._snapshots: dict[str, list[PriceSnapshot]] = {}
        self._last_alert_time: dict[str, float] = {}

    def record_price(self, condition_id: str, price: float):
        now = time.time()
        if condition_id not in self._snapshots:
            self._snapshots[condition_id] = []
        self._snapshots[condition_id].append(PriceSnapshot(price=price, timestamp=now))
        cutoff = now - WINDOW_SECONDS * 2
        self._snapshots[condition_id] = [
            s for s in self._snapshots[condition_id] if s.timestamp > cutoff
        ]

    def detect_sudden_move(self, condition_id: str) -> SentimentAlert | None:
        snaps = self._snapshots.get(condition_id, [])
        if len(snaps) < 2:
            return None

        now = time.time()
        if condition_id in self._last_alert_time:
            if now - self._last_alert_time[condition_id] < COOLDOWN_PER_MARKET:
                return None

        current = snaps[-1]
        for s in snaps:
            if current.timestamp - s.timestamp < 60:
                continue
            if current.timestamp - s.timestamp > WINDOW_SECONDS:
                continue
            if s.price <= 0:
                continue
            change = (current.price - s.price) / s.price
            if abs(change) >= MOVE_THRESHOLD_PCT:
                self._last_alert_time[condition_id] = now
                return SentimentAlert(
                    condition_id=condition_id,
                    token_id="",
                    title="",
                    price_before=s.price,
                    price_after=current.price,
                    change_pct=change,
                    window_seconds=int(current.timestamp - s.timestamp),
                )
        return None

    async def scan_markets_for_moves(self, markets: list[dict]) -> list[SentimentAlert]:
        """Record current prices and check for sudden moves."""
        alerts: list[SentimentAlert] = []
        for m in markets:
            cid = m.get("condition_id", m.get("conditionId", ""))
            if not cid:
                continue

            tokens = m.get("tokens", [])
            price = 0.5
            token_id = ""
            if tokens:
                for t in tokens:
                    if t.get("outcome", "").lower() == "yes":
                        price = float(t.get("price", 0.5))
                        token_id = t.get("token_id", "")
                        break
            if price == 0.5 and m.get("outcomePrices"):
                try:
                    import json
                    prices = m["outcomePrices"]
                    if isinstance(prices, str):
                        prices = json.loads(prices)
                    price = float(prices[0])
                except Exception:
                    pass

            vol = float(m.get("volume_num_24hr", m.get("volume24hr", 0)) or 0)
            if vol < MIN_VOLUME_24H:
                continue

            self.record_price(cid, price)
            alert = self.detect_sudden_move(cid)
            if alert:
                alert.token_id = token_id
                alert.title = m.get("question", m.get("title", ""))
                alerts.append(alert)

        return alerts

    async def evaluate_alert(
        self, alert: SentimentAlert, config: dict
    ) -> dict:
        """Use LLM to decide if a sudden move is an overreaction."""
        direction = "up" if alert.change_pct > 0 else "down"
        magnitude = abs(alert.change_pct) * 100

        analysis = await llm_analyzer.analyze_market(
            question=alert.title,
            current_price=alert.price_after,
            description=(
                f"This market just moved {magnitude:.1f}% {direction} "
                f"in {alert.window_seconds // 60} minutes "
                f"(from {alert.price_before:.2f} to {alert.price_after:.2f}). "
                f"Evaluate whether this move is justified or an overreaction."
            ),
        )

        llm_prob = analysis.get("estimated_probability", alert.price_after)
        edge = llm_prob - alert.price_after

        is_overreaction = False
        if alert.change_pct > 0 and edge < -0.03:
            is_overreaction = True
        elif alert.change_pct < 0 and edge > 0.03:
            is_overreaction = True

        side = ""
        if is_overreaction:
            side = "buy" if alert.change_pct < 0 else "sell"

        max_pos = float(config.get("max_position_size", 50.0))
        bankroll = float(config.get("max_total_exposure", 500.0))
        confidence = analysis.get("confidence", 0.0)
        fee = edge_validator.get_fee_rate("")
        bet_size, kelly = edge_validator.quarter_kelly(
            llm_prob, alert.price_after, confidence, bankroll, fee
        )
        bet_size = min(bet_size, max_pos)

        return {
            "is_overreaction": is_overreaction,
            "side": side,
            "llm_analysis": analysis,
            "edge": edge,
            "kelly": kelly,
            "bet_size": bet_size,
            "reasoning": analysis.get("reasoning", ""),
        }

    async def record_alert(
        self, alert: SentimentAlert, verdict: str, action: str
    ):
        db = await get_db()
        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                """INSERT INTO sentiment_alerts
                (condition_id, market_title, token_id, price_before, price_after,
                 change_pct, window_seconds, llm_verdict, action_taken, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alert.condition_id,
                    alert.title,
                    alert.token_id,
                    alert.price_before,
                    alert.price_after,
                    alert.change_pct,
                    alert.window_seconds,
                    verdict,
                    action,
                    now,
                ),
            )
            await db.commit()
        finally:
            await db.close()

    async def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM sentiment_alerts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()


sentiment_monitor = SentimentMonitor()
