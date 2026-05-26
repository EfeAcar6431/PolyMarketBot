import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from database import get_db, get_config

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    approved: bool
    reason: str
    adjusted_size: float


class RiskManager:
    def __init__(self):
        self._kill_switch = False
        self._last_trade_time: datetime | None = None

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def activate_kill_switch(self):
        self._kill_switch = True
        logger.warning("KILL SWITCH ACTIVATED")

    def deactivate_kill_switch(self):
        self._kill_switch = False
        logger.info("Kill switch deactivated")

    async def check_trade(
        self, side: str, size: float, price: float
    ) -> RiskCheck:
        if self._kill_switch:
            return RiskCheck(approved=False, reason="Kill switch is active", adjusted_size=0.0)

        config = await get_config()
        max_position = float(config.get("max_position_size", 50.0))
        max_exposure = float(config.get("max_total_exposure", 500.0))
        max_daily_loss = float(config.get("max_daily_loss", 100.0))
        cooldown = int(config.get("trade_cooldown", 60))

        if self._last_trade_time:
            elapsed = (datetime.now(timezone.utc) - self._last_trade_time).total_seconds()
            if elapsed < cooldown:
                return RiskCheck(
                    approved=False,
                    reason=f"Cooldown active: {cooldown - elapsed:.0f}s remaining",
                    adjusted_size=0.0,
                )

        if size > max_position:
            size = max_position

        if size * price < 0.10:
            return RiskCheck(approved=False, reason="Trade too small", adjusted_size=0.0)

        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT COALESCE(SUM(size * price), 0) as total FROM trades WHERE status = 'filled'"
            )
            row = await cursor.fetchone()
            current_exposure = float(row["total"])

            if current_exposure + (size * price) > max_exposure:
                remaining = max_exposure - current_exposure
                if remaining <= 0:
                    return RiskCheck(approved=False, reason="Max total exposure reached", adjusted_size=0.0)
                size = min(size, remaining / price)

            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
            cursor = await db.execute(
                "SELECT COALESCE(SUM(pnl), 0) as daily_pnl FROM trades WHERE created_at >= ?",
                (today_start,),
            )
            row = await cursor.fetchone()
            daily_pnl = float(row["daily_pnl"])

            if daily_pnl < -max_daily_loss:
                self.activate_kill_switch()
                return RiskCheck(
                    approved=False,
                    reason=f"Daily loss limit hit (${abs(daily_pnl):.2f}). Kill switch auto-activated.",
                    adjusted_size=0.0,
                )
        finally:
            await db.close()

        return RiskCheck(approved=True, reason="Approved", adjusted_size=round(size, 2))

    def record_trade(self):
        self._last_trade_time = datetime.now(timezone.utc)


risk_manager = RiskManager()
