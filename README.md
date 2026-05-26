# PolyMarketBot

> AI-powered trading agent for [Polymarket](https://polymarket.com) with a real-time dashboard, multiple autonomous strategies, and institutional-grade risk controls.

---

## Overview

PolyMarketBot is a full-stack autonomous trading system for prediction markets. A **GPT-4o-powered agent** continuously scans Polymarket, identifies mispriced outcomes across multiple strategies, and executes trades through the Polymarket CLOB API — all while a live Next.js dashboard gives you full visibility and control.

### Strategies

| # | Name | Description |
|---|------|-------------|
| A | **Main Agent** | LLM evaluates markets, estimates true probability, and sizes trades using quant signals (momentum + mean reversion) |
| B | **Live Scalper** | Fast statistical pre-filter runs every 15–30s. Escalates to LLM agent only when signals cross threshold |
| C | **Market Sniper** | Monitors Polymarket WebSocket + Gamma API for newly listed markets and snipes initial mispricings before smart money arrives |

Additional modules: **Whale Tracker** (follows high-conviction wallets), **Sentiment Monitor** (detects sharp price moves), **Odds Comparator** (benchmarks against external sportsbooks), and **News Fetcher** (enriches LLM context).

---

## Architecture

```
┌─────────────────────────────┐     ┌──────────────────────────────┐
│  Next.js Dashboard (:3000)  │◄───►│  FastAPI Backend (:8000)      │
│                             │ WS  │                               │
│  • Dashboard & P&L          │  +  │  • Strategy A — Main Agent    │
│  • Markets browser          │REST │  • Strategy B — Live Scalper  │
│  • Strategies control       │     │  • Strategy C — Sniper        │
│  • Trade history            │     │  • Whale Tracker              │
│  • Agent thoughts           │     │  • Sentiment Monitor          │
│  • Whale activity           │     │  • Risk Manager               │
│  • Live activity feed       │     │  • Edge Validator             │
└─────────────────────────────┘     └────────────┬─────────────────┘
                                                 │
                                    ┌────────────┼────────────┐
                                    ▼            ▼            ▼
                               Polymarket    OpenAI API    SQLite DB
                               CLOB + Gamma  (GPT-4o-mini)
```

---

## Tech Stack

**Backend** — Python 3.11+, FastAPI, py-clob-client, OpenAI SDK, aiosqlite, httpx, websockets

**Frontend** — Next.js 14, React, TypeScript, Tailwind CSS, Recharts, TanStack React Query

**Real-time** — WebSocket feed broadcasting live agent events to the dashboard

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Polymarket-compatible Ethereum wallet funded with USDC on Polygon
- An [OpenAI API key](https://platform.openai.com/api-keys)
- *(Optional)* An [The Odds API key](https://the-odds-api.com/) for external line comparisons

---

## Setup

### 1. Clone & configure environment

```bash
git clone https://github.com/EfeAcar6431/PolyMarketBot.git
cd PolyMarketBot
cp .env.example .env
# Fill in your POLYMARKET_PRIVATE_KEY and OPENAI_API_KEY
```

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values. **Never commit `.env`.**

| Variable | Required | Description |
|----------|----------|-------------|
| `POLYMARKET_PRIVATE_KEY` | Yes | Ethereum private key for your Polygon wallet |
| `OPENAI_API_KEY` | Yes | OpenAI key for GPT-4o-mini inference |
| `POLYMARKET_CHAIN_ID` | No | Polygon chain ID (default `137`) |
| `AGENT_SCAN_INTERVAL` | No | Seconds between main agent cycles (default `300`) |
| `MAX_POSITION_SIZE` | No | Max USDC per position (default `50`) |
| `MAX_TOTAL_EXPOSURE` | No | Max total USDC across all positions (default `500`) |
| `MAX_DAILY_LOSS` | No | Daily loss limit before kill switch (default `100`) |
| `TRADE_COOLDOWN_SECONDS` | No | Minimum seconds between trades (default `60`) |
| `ODDS_API_KEY` | No | The Odds API key for external line comparisons |
| `DATABASE_URL` | No | SQLite path relative to `backend/` (default `data.db`) |

---

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Dashboard** | Portfolio summary, cumulative P&L chart, active positions, agent status |
| **Markets** | Browse and search Polymarket events, filter by category, run AI analysis on any market |
| **Strategies** | Start/stop each strategy independently, configure parameters, view per-strategy stats |
| **Trades** | Full trade history, win rate, per-strategy performance breakdown |
| **Thoughts** | Live stream of the agent's LLM reasoning and decision logs |
| **Whales** | Track high-conviction wallets and their recent market activity |

The **Live Feed** sidebar shows real-time agent events across all pages via WebSocket.

---

## How the Main Agent Works

Each cycle (default every 5 minutes):

1. **Scan** — Fetch top markets by 24h volume from the Polymarket Gamma API
2. **Filter** — Edge validator applies fee schedule and preferred-category weights
3. **Analyze** — LLM estimates the true probability of each outcome and calculates edge over the market price
4. **Score** — Quant engine applies momentum + mean reversion signals to produce a combined trade score
5. **Risk check** — Validates against position limits, exposure caps, daily loss budget, and cooldown timer
6. **Execute** — Places limit orders via the Polymarket CLOB API for approved trades
7. **Log** — Records every decision to SQLite and broadcasts to the dashboard via WebSocket

---

## Risk Controls

All configurable from the dashboard or `.env`:

- **Max position size** — cap per individual market (default $50)
- **Max total exposure** — cap across all open positions (default $500)
- **Max daily loss** — automatic kill switch when breached (default $100)
- **Trade cooldown** — minimum gap between trades (default 60s)
- **Kill switch** — instantly cancels all open orders and halts all strategies

---

## Project Structure

```
PolyMarketBot/
├── backend/
│   ├── main.py               # FastAPI app entry point
│   ├── config.py             # Settings from environment
│   ├── database.py           # SQLite helpers
│   ├── models.py             # Pydantic models
│   ├── routers/              # API route handlers
│   │   ├── agent.py
│   │   ├── agent_plans.py
│   │   ├── markets.py
│   │   ├── trades.py
│   │   ├── portfolio.py
│   │   ├── whales.py
│   │   ├── sentiment.py
│   │   ├── odds.py
│   │   ├── scalper.py
│   │   ├── sniper.py
│   │   ├── market_making.py
│   │   └── ws.py             # WebSocket broadcast
│   └── services/             # Core logic
│       ├── trading_agent.py  # GPT-4o agent + tool use
│       ├── live_scalper.py   # Strategy B
│       ├── market_sniper.py  # Strategy C
│       ├── agent_runner.py   # Strategy A orchestrator
│       ├── llm_analyzer.py   # Market analysis via LLM
│       ├── quant_signals.py  # Momentum + mean reversion
│       ├── edge_validator.py # Fee-adjusted edge calculation
│       ├── risk_manager.py   # Position + drawdown limits
│       ├── position_manager.py
│       ├── whale_tracker.py
│       ├── sentiment_monitor.py
│       ├── odds_comparator.py
│       ├── news_fetcher.py
│       └── polymarket.py     # Polymarket API client
└── frontend/
    ├── app/
    │   ├── page.tsx          # Dashboard
    │   ├── markets/
    │   ├── strategies/
    │   ├── trades/
    │   ├── thoughts/
    │   └── whales/
    ├── components/           # Shared UI components
    └── lib/                  # API client helpers
```

---

## Disclaimer

This software is for educational and research purposes only. Prediction market trading involves real financial risk. Never trade with funds you cannot afford to lose. Past performance of any strategy does not guarantee future results.

---

## License

[Apache 2.0](LICENSE)
