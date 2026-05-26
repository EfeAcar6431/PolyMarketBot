import logging
from dataclasses import dataclass

from services.polymarket import polymarket_service

logger = logging.getLogger(__name__)

FEE_SCHEDULE: dict[str, float] = {
    "geopolitics": 0.0,
    "politics": 0.01,
    "finance": 0.01,
    "tech": 0.01,
    "economics": 0.01,
    "sports": 0.0075,
    "culture": 0.01,
    "weather": 0.01,
    "crypto": 0.018,
}

PREFERRED_CATEGORIES = {"geopolitics", "politics", "finance", "tech"}
DEFAULT_FEE = 0.01


@dataclass
class EdgeResult:
    approved: bool
    reason: str
    bet_size: float
    kelly_fraction: float
    fee_rate: float
    available_depth: float


class EdgeValidator:
    @staticmethod
    def get_fee_rate(category: str) -> float:
        return FEE_SCHEDULE.get(category.lower().strip(), DEFAULT_FEE)

    @staticmethod
    def is_preferred_category(category: str) -> bool:
        return category.lower().strip() in PREFERRED_CATEGORIES

    @staticmethod
    def kelly_bet(
        true_probability: float,
        market_price: float,
        confidence: float,
        bankroll: float,
        fee_rate: float,
        kelly_multiplier: float = 0.25,
    ) -> tuple[float, float]:
        """Returns (bet_size, kelly_fraction). Negative kelly means no edge."""
        effective_price = market_price + fee_rate
        if effective_price >= 1.0 or effective_price <= 0.0:
            return 0.0, 0.0

        edge = true_probability - effective_price
        if edge <= 0:
            return 0.0, -abs(edge)

        odds = (1.0 - effective_price) / effective_price
        if odds <= 0:
            return 0.0, 0.0

        kelly = (odds * true_probability - (1.0 - true_probability)) / odds
        if kelly <= 0:
            return 0.0, kelly

        adjusted_kelly = kelly * kelly_multiplier * confidence
        bet = bankroll * adjusted_kelly
        return round(bet, 2), round(adjusted_kelly, 4)

    @staticmethod
    def quarter_kelly(
        llm_probability: float,
        market_price: float,
        confidence: float,
        bankroll: float,
        fee_rate: float,
    ) -> tuple[float, float]:
        """Backward-compatible wrapper using 0.25x Kelly."""
        return EdgeValidator.kelly_bet(
            llm_probability, market_price, confidence, bankroll, fee_rate, 0.25
        )

    async def check_orderbook_depth(
        self, token_id: str, side: str, target_price: float, required_size: float
    ) -> tuple[bool, float]:
        """Check if orderbook has enough liquidity. Returns (has_depth, available_size)."""
        if not token_id:
            return False, 0.0
        try:
            book = await polymarket_service.get_orderbook(token_id)
            orders = book.get("asks" if side == "buy" else "bids", [])
            available = 0.0
            for order in orders:
                price = float(order.get("price", 0))
                size = float(order.get("size", 0))
                if side == "buy" and price <= target_price * 1.03:
                    available += size
                elif side == "sell" and price >= target_price * 0.97:
                    available += size
            return available >= required_size, round(available, 2)
        except Exception as e:
            logger.warning("Orderbook depth check failed: %s", e)
            return True, 0.0  # fail-open so we don't block every trade

    async def validate(
        self,
        analysis: dict,
        market: dict,
        bankroll: float,
        max_position: float,
        kelly_multiplier: float = 0.25,
    ) -> EdgeResult:
        category = (market.get("category", "") or market.get("groupItemTitle", "") or "").lower()
        fee_rate = self.get_fee_rate(category)

        llm_prob = analysis.get("estimated_probability", 0.5)
        market_price = analysis.get("current_price", 0.5)
        confidence = analysis.get("confidence", 0.0)

        bet_size, kelly_frac = self.kelly_bet(
            true_probability=llm_prob,
            market_price=market_price,
            confidence=confidence,
            bankroll=bankroll,
            fee_rate=fee_rate,
            kelly_multiplier=kelly_multiplier,
        )

        if kelly_frac <= 0:
            return EdgeResult(
                approved=False,
                reason=f"No edge after {fee_rate*100:.1f}% fee (Kelly={kelly_frac:.4f})",
                bet_size=0.0,
                kelly_fraction=kelly_frac,
                fee_rate=fee_rate,
                available_depth=0.0,
            )

        bet_size = min(bet_size, max_position)
        if bet_size < 1.0:
            return EdgeResult(
                approved=False,
                reason=f"Bet size too small (${bet_size:.2f})",
                bet_size=bet_size,
                kelly_fraction=kelly_frac,
                fee_rate=fee_rate,
                available_depth=0.0,
            )

        token_id = analysis.get("token_id", "")
        side = "buy" if analysis.get("edge", 0) > 0 else "sell"
        has_depth, depth = await self.check_orderbook_depth(
            token_id, side, market_price, bet_size
        )
        if not has_depth:
            return EdgeResult(
                approved=False,
                reason=f"Insufficient orderbook depth (need ${bet_size:.0f}, have ${depth:.0f})",
                bet_size=bet_size,
                kelly_fraction=kelly_frac,
                fee_rate=fee_rate,
                available_depth=depth,
            )

        return EdgeResult(
            approved=True,
            reason="Edge validated",
            bet_size=bet_size,
            kelly_fraction=kelly_frac,
            fee_rate=fee_rate,
            available_depth=depth,
        )


edge_validator = EdgeValidator()
