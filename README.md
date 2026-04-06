# Deriv Multi-Asset Trading Bot

Automated trading bot for Deriv's synthetic indices using **multiplier contracts**. Supports dual trading strategies — a **Conservative** top-down market structure analysis and a fast **Scalping** EMA-based approach — each with independent risk management, all orchestrated via a FastAPI backend with real-time WebSocket updates.

---

## ✨ Features

### Trading Strategies

| | Conservative | Scalping |
|---|---|---|
| **Timeframes** | 6 (1W → 1D → 4H → 1H → 5M → 1M) | 3 (1H → 5M → 1M) |
| **Trend Detection** | Swing High/Low structure | EMA 9 vs EMA 21 crossover |
| **Entry Validation** | Momentum close > 1.5× ATR or weak retest | ADX > 18 + RSI band filter |
| **TP/SL** | Dynamic (nearest structure level / swing point) | ATR-based (2.25× ATR TP / 1.5× ATR SL) |
| **Min R:R** | 2.5:1 | 1.5:1 |
| **Max Concurrent** | 2 trades | 4 trades |
| **Daily Trade Cap** | Unlimited (risk-limited) | 80 |

Strategies are selected per-user from the frontend dashboard and managed via the **Strategy Registry** (`strategy_registry.py`).

### Risk Management

- **Per-trade trailing stops** — multi-tier trailing that widens as profit grows
- **Breakeven protection** — locks stop at −5% loss once trade reaches +20% profit
- **Stagnation exit** — closes losing trades stuck too long (720s conservative / 120s scalping)
- **Daily loss limits** — configurable multiplier of stake
- **Consecutive loss cooldown** — pauses after N losses in a row
- **Runaway trade guardrail** (scalping) — blocks if 10+ trades fire within 10 minutes
- **Parabolic spike detection** — rejects entries into extended moves

### Multi-Asset Support

Monitors and trades the following Deriv Synthetic Indices simultaneously:

| Symbol | Description | Multiplier |
|---|---|---|
| `R_25` | Volatility 25 Index | 160× |
| `R_50` | Volatility 50 Index | 100× |
| `R_75` | Volatility 75 Index | 80× |
| `R_100` | Volatility 100 Index | 60× |
| `1HZ75V` | Volatility 75 (1s) Index | 50× |
| `1HZ90V` | Volatility 90 (1s) Index | 45× |

Each asset has tuned entry-distance and movement thresholds in `config.py`.

### Backend & API

- **FastAPI** REST API with Swagger docs at `/docs`
- **Supabase** for user auth, trade history, and profile persistence
- **WebSocket** endpoint (`/ws`) for real-time trade updates
- **Telegram** notifications (trade opens, closes, daily summaries, errors)
- **Rate limiting** via SlowAPI
- **Security headers** (CSP, HSTS, X-Frame-Options, Referrer-Policy)

#### API Routes

| Prefix | Tag | Purpose |
|---|---|---|
| `/api/v1/auth` | Authentication | Login, register, profile |
| `/api/v1/bot` | Bot Control | Start, stop, status |
| `/api/v1/trades` | Trades | History, active positions |
| `/api/v1/monitor` | Monitoring | Health, performance stats |
| `/api/v1/config` | Configuration | Strategy & risk settings |
| `/ws` | WebSocket | Live trade stream |

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        FastAPI (app/)                          │
│  api/ ─ REST endpoints        ws/ ─ WebSocket live feed       │
│  bot/ ─ Bot lifecycle mgr     core/ ─ Settings, auth, logging │
│  schemas/ ─ Pydantic models   services/ ─ Business logic      │
└───────────────────────┬────────────────────────────────────────┘
                        │ controls
┌───────────────────────▼────────────────────────────────────────┐
│                     main.py (TradingBot)                       │
│  Orchestrates scan → analyze → execute loop across all assets  │
└────┬──────────┬───────────┬────────────┬───────────────────────┘
     │          │           │            │
┌────▼────┐ ┌──▼────────┐ ┌▼──────────┐ ┌▼──────────────┐
│  Data   │ │ Strategy  │ │  Risk     │ │ Trade Engine  │
│ Fetcher │ │ Registry  │ │ Manager   │ │ (WebSocket)   │
│         │ │           │ │           │ │               │
│ Deriv   │ │Conservative│ │Conservative│ │ Open / Close │
│ WS API  │ │ Scalping  │ │ Scalping  │ │ Monitor TP/SL│
└─────────┘ └───────────┘ └───────────┘ └───────────────┘
```

### Key Files

| File | Purpose |
|---|---|
| `main.py` | Bot controller — init, scan loop, trading cycle |
| `config.py` | All conservative strategy & global parameters |
| `scalping_config.py` | All scalping-specific parameters |
| `strategy_registry.py` | Maps strategy names → (Strategy, RiskManager) classes |
| `base_strategy.py` | Abstract strategy interface |
| `conservative_strategy.py` | 6-timeframe top-down strategy |
| `scalping_strategy.py` | 3-timeframe EMA scalping strategy |
| `base_risk_manager.py` | Abstract risk manager interface |
| `conservative_risk_manager.py` | Risk manager for conservative strategy |
| `scalping_risk_manager.py` | Risk manager for scalping strategy |
| `risk_manager.py` | Full-featured production risk manager (legacy + active) |
| `trade_engine.py` | Deriv WebSocket trade execution & monitoring |
| `data_fetcher.py` | Multi-timeframe OHLC data via Deriv API |
| `indicators.py` | ATR, RSI, ADX, EMA, SMA, Bollinger, MACD, etc. |
| `telegram_notifier.py` | Telegram bot notifications |
| `utils.py` | Logging, helpers, token bucket rate limiter |
| `app/main.py` | FastAPI entry point |

---

## 🚀 Quick Setup

### Prerequisites

- **Python 3.11+** (see `runtime.txt`)
- Deriv account with API token
- Supabase project (for auth & trade storage)
- Telegram bot token *(optional, for notifications)*

### Installation

```bash
git clone <repo-url>
cd R50BOT

python -m venv venv
# Windows
venv\Scripts\activate
# Linux / Mac
source venv/bin/activate

pip install -r requirements.txt
```

### Configuration

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Key variables:

| Variable | Required | Description |
|---|---|---|
| `DERIV_API_TOKEN` | ✅ | Your Deriv API token |
| `DERIV_APP_ID` | ✅ | Deriv app ID (default `1089`) |
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase service role key |
| `SUPABASE_ANON_KEY` | ✅ | Supabase anonymous key |
| `DERIV_API_KEY_ENCRYPTION_SECRET` | ✅ | Secret used to encrypt Deriv API keys before storing in Supabase |
| `TELEGRAM_BOT_TOKEN` | ❌ | Telegram bot token for notifications |
| `TELEGRAM_CHAT_ID` | ❌ | Telegram chat ID |
| `SCALPING_BOT_ENABLED` | ❌ | Set `true` to enable the scalping strategy |
| `BOT_AUTO_START` | ❌ | Set `true` to auto-start bot on deploy |
| `CORS_ORIGINS` | ❌ | Comma-separated allowed frontend origins |

### Database Setup

Run the SQL migrations in your Supabase SQL Editor:

```bash
# 1. Core schema
supabase_setup.sql

# 2. Trades table
supabase_trades.sql

# 3. Row-Level Security policies
secure_rls.sql
```

### Running Locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### Admin Setup

```bash
python create_admin.py your@email.com
```

---

## ☁️ Deployment

### Render

1. Connect your GitHub repository.
2. Render auto-detects `render.yaml`.
3. Add environment variables in the dashboard.
4. If you use Render Redis, set `REDIS_URL` for the API service.

### Railway

1. Connect your GitHub repository.
2. Railway auto-detects `railway.json` and `Procfile`.
3. Add environment variables in the dashboard.

The `Procfile` runs:

```
worker: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

---

## 🧪 Tests

```bash
pytest tests/
```

---

## 📄 License

MIT
