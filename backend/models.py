from pydantic import BaseModel


class TradeOut(BaseModel):
    id: int
    market_id: str
    market_question: str
    token_id: str
    side: str
    price: float
    size: float
    status: str
    pnl: float
    strategy_reason: str
    order_id: str
    created_at: str


class TradeStats(BaseModel):
    total_trades: int
    total_pnl: float
    win_count: int
    loss_count: int
    win_rate: float
    best_trade: float
    worst_trade: float
    avg_trade_pnl: float


class PortfolioSummary(BaseModel):
    balance: float
    total_pnl: float
    active_positions: int
    win_rate: float
    positions: list


class AgentStatus(BaseModel):
    status: str
    config: dict


class AgentConfigUpdate(BaseModel):
    paper_mode: bool | None = None
    scan_interval: int | None = None
    max_position_size: float | None = None
    max_total_exposure: float | None = None
    max_daily_loss: float | None = None
    trade_cooldown: int | None = None
    min_edge_threshold: float | None = None
    llm_weight: float | None = None
    quant_weight: float | None = None
    whale_tracking: bool | None = None
    sentiment_monitoring: bool | None = None
    market_making: bool | None = None
    mm_order_size: float | None = None
    odds_comparison: bool | None = None
    kelly_multiplier_default: float | None = None
    kelly_multiplier_odds: float | None = None
    odds_min_edge: float | None = None
    whale_conviction_enabled: bool | None = None
    whale_min_trade_size: float | None = None
    whale_kelly_multiplier: float | None = None
    whale_sports_only: bool | None = None
    whale_max_agent_steps: int | None = None
    scalper_enabled: bool | None = None
    scalper_interval: int | None = None
    scalper_position_size: float | None = None
    scalper_max_positions: int | None = None
    scalper_signal_threshold: float | None = None
    scalper_target_pct: float | None = None
    scalper_stop_pct: float | None = None
    sniper_enabled: bool | None = None
    sniper_min_edge: float | None = None
    sniper_max_bet: float | None = None
    sniper_kelly_multiplier: float | None = None
    sniper_llm_timeout: float | None = None
    sniper_max_agent_steps: int | None = None
    position_reeval_interval: int | None = None


class MarketAnalysis(BaseModel):
    market_id: str
    question: str
    current_price: float
    llm_probability: float
    confidence: float
    edge: float
    reasoning: str


class LogEntry(BaseModel):
    id: int
    level: str
    message: str
    metadata: dict
    created_at: str
