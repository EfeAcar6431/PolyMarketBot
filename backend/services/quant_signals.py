import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    score: float  # -1.0 (strong sell) to +1.0 (strong buy)
    recommended_size: float
    components: dict = field(default_factory=dict)


class QuantSignalEngine:
    def __init__(self):
        self._price_history: dict[str, list[float]] = {}

    def record_price(self, token_id: str, price: float):
        if token_id not in self._price_history:
            self._price_history[token_id] = []
        self._price_history[token_id].append(price)
        if len(self._price_history[token_id]) > 100:
            self._price_history[token_id] = self._price_history[token_id][-100:]

    def momentum_signal(self, token_id: str, window: int = 10) -> float:
        history = self._price_history.get(token_id, [])
        if len(history) < window + 1:
            return 0.0
        recent = history[-window:]
        change = recent[-1] - recent[0]
        return max(-1.0, min(1.0, change * 10))

    def mean_reversion_signal(self, token_id: str, window: int = 20) -> float:
        history = self._price_history.get(token_id, [])
        if len(history) < window:
            return 0.0
        recent = history[-window:]
        mean = sum(recent) / len(recent)
        current = recent[-1]
        deviation = current - mean
        return max(-1.0, min(1.0, -deviation * 15))

    def volume_filter(self, volume_24h: float, min_volume: float = 1000.0) -> bool:
        return volume_24h >= min_volume

    def compute_signal(
        self,
        token_id: str,
        current_price: float,
        volume_24h: float = 0.0,
        llm_edge: float = 0.0,
        llm_weight: float = 0.6,
        quant_weight: float = 0.4,
        max_position: float = 50.0,
    ) -> Signal:
        self.record_price(token_id, current_price)

        if not self.volume_filter(volume_24h):
            return Signal(score=0.0, recommended_size=0.0, components={"reason": "insufficient_volume"})

        mom = self.momentum_signal(token_id)
        mr = self.mean_reversion_signal(token_id)
        quant_score = 0.6 * mr + 0.4 * mom

        llm_score = max(-1.0, min(1.0, llm_edge * 10))
        combined = llm_weight * llm_score + quant_weight * quant_score
        combined = max(-1.0, min(1.0, combined))

        size = abs(combined) * max_position

        return Signal(
            score=combined,
            recommended_size=round(size, 2),
            components={
                "momentum": round(mom, 4),
                "mean_reversion": round(mr, 4),
                "quant_combined": round(quant_score, 4),
                "llm_score": round(llm_score, 4),
                "final_combined": round(combined, 4),
            },
        )


quant_engine = QuantSignalEngine()
