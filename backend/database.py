import aiosqlite
import json
from datetime import datetime, timezone
from config import settings

DB_PATH = settings.database_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    market_question TEXT DEFAULT '',
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    pnl REAL DEFAULT 0.0,
    strategy_reason TEXT DEFAULT '',
    order_id TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS whale_watchlist (
    wallet TEXT PRIMARY KEY,
    username TEXT DEFAULT '',
    category TEXT DEFAULT 'OVERALL',
    pnl REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0,
    total_trades INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    added_at TEXT NOT NULL,
    last_checked_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS whale_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    outcome TEXT DEFAULT '',
    condition_id TEXT DEFAULT '',
    market_title TEXT DEFAULT '',
    market_slug TEXT DEFAULT '',
    tx_hash TEXT DEFAULT '',
    whale_timestamp INTEGER NOT NULL,
    followed INTEGER DEFAULT 0,
    follow_reason TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sentiment_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    market_title TEXT DEFAULT '',
    token_id TEXT DEFAULT '',
    price_before REAL NOT NULL,
    price_after REAL NOT NULL,
    change_pct REAL NOT NULL,
    window_seconds INTEGER NOT NULL,
    llm_verdict TEXT DEFAULT '',
    action_taken TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mm_inventory (
    token_id TEXT PRIMARY KEY,
    condition_id TEXT DEFAULT '',
    market_title TEXT DEFAULT '',
    yes_balance REAL DEFAULT 0.0,
    no_balance REAL DEFAULT 0.0,
    target_spread REAL DEFAULT 0.04,
    active INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    token_id TEXT NOT NULL,
    condition_id TEXT DEFAULT '',
    market_title TEXT DEFAULT '',
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL DEFAULT 0.0,
    size REAL NOT NULL,
    exit_target REAL DEFAULT 0.0,
    stop_loss REAL DEFAULT 0.0,
    hold_duration TEXT DEFAULT 'settlement',
    status TEXT NOT NULL DEFAULT 'open',
    pnl REAL DEFAULT 0.0,
    agent_plan_id INTEGER,
    opened_at TEXT NOT NULL,
    closed_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    trigger_summary TEXT DEFAULT '',
    context_json TEXT DEFAULT '{}',
    reasoning_chain TEXT DEFAULT '[]',
    plan_json TEXT DEFAULT '{}',
    executed INTEGER DEFAULT 0,
    risk_rejection_reason TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sniper_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    market_title TEXT DEFAULT '',
    token_id TEXT DEFAULT '',
    detected_at TEXT NOT NULL,
    initial_price REAL DEFAULT 0.5,
    agent_assessment TEXT DEFAULT '',
    action TEXT DEFAULT 'skip',
    bet_size REAL DEFAULT 0.0,
    bet_side TEXT DEFAULT '',
    price_5min_later REAL
);

CREATE TABLE IF NOT EXISTS scalper_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL,
    price REAL NOT NULL,
    bid_depth REAL DEFAULT 0.0,
    ask_depth REAL DEFAULT 0.0,
    volume_24h REAL DEFAULT 0.0,
    spread REAL DEFAULT 0.0,
    recorded_at TEXT NOT NULL
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        defaults = {
            "agent_status": "stopped",
            "paper_mode": "true",
            "scan_interval": str(settings.agent_scan_interval),
            "max_position_size": str(settings.max_position_size),
            "max_total_exposure": str(settings.max_total_exposure),
            "max_daily_loss": str(settings.max_daily_loss),
            "trade_cooldown": str(settings.trade_cooldown_seconds),
            "min_edge_threshold": "0.05",
            "llm_weight": "0.6",
            "quant_weight": "0.4",
            "whale_tracking": "true",
            "sentiment_monitoring": "true",
            "market_making": "false",
            "mm_order_size": "20",
            "odds_comparison": "true",
            "kelly_multiplier_default": "0.25",
            "kelly_multiplier_odds": "0.5",
            "odds_min_edge": "0.03",
            "odds_cache_minutes": "120",
            "whale_conviction_enabled": "true",
            "whale_min_trade_size": "1000",
            "whale_kelly_multiplier": "0.5",
            "whale_sports_only": "true",
            "whale_max_agent_steps": "5",
            "scalper_enabled": "false",
            "scalper_interval": "30",
            "scalper_position_size": "15",
            "scalper_max_positions": "5",
            "scalper_signal_threshold": "0.3",
            "scalper_target_pct": "0.04",
            "scalper_stop_pct": "0.03",
            "sniper_enabled": "false",
            "sniper_min_edge": "0.10",
            "sniper_max_bet": "50",
            "sniper_kelly_multiplier": "0.35",
            "sniper_llm_timeout": "8",
            "sniper_max_agent_steps": "3",
            "position_reeval_interval": "5",
        }
        for k, v in defaults.items():
            await db.execute(
                "INSERT OR IGNORE INTO agent_config (key, value) VALUES (?, ?)",
                (k, v),
            )
        await db.commit()
    finally:
        await db.close()


async def log_event(level: str, message: str, metadata: dict | None = None):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO agent_logs (level, message, metadata_json, created_at) VALUES (?, ?, ?, ?)",
            (level, message, json.dumps(metadata or {}), datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
    finally:
        await db.close()


async def insert_trade(
    market_id: str,
    market_question: str,
    token_id: str,
    side: str,
    price: float,
    size: float,
    status: str,
    strategy_reason: str,
    order_id: str = "",
) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO trades
            (market_id, market_question, token_id, side, price, size, status, strategy_reason, order_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (market_id, market_question, token_id, side, price, size, status, strategy_reason, order_id, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_config() -> dict:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key, value FROM agent_config")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        await db.close()


async def set_config(key: str, value: str):
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO agent_config (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()
    finally:
        await db.close()
