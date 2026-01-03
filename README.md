# Deriv R_25 Trading Bot

**Professional automated trading bot for Deriv's R_25 synthetic index using top-down market structure analysis.**

Live Demo: https://r-25v1.onrender.com/docs/

---

## Key Features

- **Top-Down Strategy** - Weekly/Daily trend analysis with 1m/5m execution
- **Multi-Timeframe Analysis** - Simultaneous analysis across 6 timeframes (1w, 1d, 4h, 1h, 5m, 1m)
- **Dynamic Risk Management** - Structure-based stops and level-based targets
- **REST API + WebSocket** - Full control and real-time monitoring
- **JWT Authentication** - Secure access control
- **Telegram Alerts** - Instant trade notifications
- **Interactive Dashboard** - Swagger UI with live documentation

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   FastAPI Application                     │
│                                                           │
│  ┌─────────┐  ┌───────────┐  ┌──────┐  ┌──────────┐   │
│  │ REST    │  │ WebSocket │  │ Auth │  │ Telegram │   │
│  │ API     │  │ Server    │  │ JWT  │  │ Notifier │   │
│  └────┬────┘  └─────┬─────┘  └──┬───┘  └────┬─────┘   │
│       └─────────────┴───────────┴───────────┘           │
│                       │                                  │
│       ┌───────────────▼───────────────┐                 │
│       │        Bot Runner Core         │                 │
│       │  ┌──────────────────────────┐ │                 │
│       │  │  Multi-Timeframe Data    │ │                 │
│       │  │  Fetcher (1w → 1m)       │ │                 │
│       │  └────────────┬─────────────┘ │                 │
│       │               │                │                 │
│       │  ┌────────────▼─────────────┐ │                 │
│       │  │  Top-Down Strategy       │ │                 │
│       │  │  • Weekly/Daily Bias     │ │                 │
│       │  │  • Level Detection       │ │                 │
│       │  │  • Momentum + Retest     │ │                 │
│       │  └────────────┬─────────────┘ │                 │
│       │               │                │                 │
│       │  ┌────────────▼─────────────┐ │                 │
│       │  │  Risk Manager            │ │                 │
│       │  │  • Daily Loss Limit      │ │                 │
│       │  │  • Position Sizing       │ │                 │
│       │  │  • Cooldown Logic        │ │                 │
│       │  └────────────┬─────────────┘ │                 │
│       │               │                │                 │
│       │  ┌────────────▼─────────────┐ │                 │
│       │  │  Trade Engine            │ │                 │
│       │  │  • Contract Execution    │ │                 │
│       │  │  • Phase Management      │ │                 │
│       │  │  • P&L Tracking          │ │                 │
│       │  └──────────────────────────┘ │                 │
│       └───────────────────────────────┘                 │
│                       │                                  │
│       ┌───────────────▼───────────────┐                 │
│       │       Deriv WebSocket API      │                 │
│       │       (R_25 Trading)           │                 │
│       └───────────────────────────────┘                 │
└──────────────────────────────────────────────────────────┘
```

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Trading Strategy](#trading-strategy)
3. [Risk Management](#risk-management)
4. [API Reference](#api-reference)
5. [Deployment](#deployment)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Prerequisites

- Python 3.13+ (or 3.10+)
- Deriv account with API token ([Get one here](https://app.deriv.com/account/api-token))
- Telegram bot token (optional, [create via @BotFather](https://t.me/BotFather))

### 2. Installation

```bash
# Clone repository
git clone https://github.com/yourusername/deriv-r25-trading-bot.git
cd deriv-r25-trading-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create `.env` file:

```env
# Deriv API (Required)
DERIV_API_TOKEN=your_deriv_api_token_here
DERIV_APP_ID=1089

# Security (Required)
JWT_SECRET_KEY=generate_with_openssl_rand_hex_32
ADMIN_PASSWORD=your_secure_password

# Telegram (Optional)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Application
ENVIRONMENT=development
BOT_AUTO_START=false
PORT=10000
```

**Generate JWT Secret:**
```bash
openssl rand -hex 32
```

### 4. Run the Bot

```bash
# Start server
uvicorn app.main:app --host 0.0.0.0 --port 10000 --reload

# Access at:
# • API Docs: http://localhost:10000/docs
# • Dashboard: http://localhost:10000/
# • Health: http://localhost:10000/health
```

### 5. Control via API

```bash
# Login
curl -X POST http://localhost:10000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Start bot (use token from login)
curl -X POST http://localhost:10000/api/v1/bot/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get status
curl http://localhost:10000/api/v1/bot/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Trading Strategy

### Top-Down Market Structure Analysis

The bot implements a professional-grade strategy used by institutional traders.

#### **Phase 1: Directional Bias (Weekly + Daily)**

```
Weekly Structure (Master Trend)
    ↓
Daily Structure (Intermediate Trend)
    ↓
Establish Directional Bias:
• Both BULLISH → Look for BUY only
• Both BEARISH → Look for SELL only  
• Conflict/Neutral → NO TRADING
```

**Why this matters:** Trading against higher timeframe trends is the #1 cause of losses. This filter ensures you're only taking trades aligned with the "big picture."

#### **Phase 2: Price Level Classification**

The bot identifies three types of levels:

| Level Type | Description | Purpose |
|------------|-------------|---------|
| **Tested** | Historical support/resistance touched multiple times | Confirms market structure |
| **Untested** | Broken levels never retested | **Primary TP targets** (price magnets) |
| **Minor** | Recent intraday highs/lows | Execution reference points |

#### **Phase 3: Entry Execution**

The bot only trades when ALL conditions align:

1. **Momentum Close**: Decisive candle close beyond a level (≥1.5x ATR)
2. **Weak Retest**: Shallow pullback (5-30%) confirming the break
3. **Middle Zone Avoidance**: Never trades in the 30-70% range between levels
4. **Direction Validation**: Signal must align with Weekly/Daily bias

#### **Phase 4: Trade Management**

- **Take Profit**: Nearest untested level (dynamic)
- **Stop Loss**: Behind last swing point (Daily structure)
- **Risk/Reward**: Minimum 1:2.0 ratio enforced

### Visual Example

```
BULLISH BIAS (Weekly + Daily aligned)
                                   
     ┌─ Untested Resistance (TP Target)
     │
───┬─┴──────────────  ← Momentum Close
   │                   
   │  ←──── Weak Retest (15% pullback)
   │                   
───┼─────────────────  ← Entry Price
   │
   │
───┴─────────────────  ← Tested Support
   
   Stop Loss ─►  (Below last swing low)
```

---

## Risk Management

### Multi-Layer Protection System

| Protection Layer | Rule | Purpose |
|------------------|------|---------|
| **Daily Loss Limit** | -$10.00 max | Preserves capital |
| **Trade Frequency** | Max 30 trades/day | Prevents overtrading |
| **Position Limit** | 1 active trade | No over-leveraging |
| **Consecutive Loss** | 3 losses → cooldown | Stops bleed during drawdowns |
| **Market Conditions** | ATR/ADX filters | Avoids hostile conditions |

### Risk Modes

The bot supports three operational modes:

#### **1. Top-Down Mode** (Default - Recommended)
```python
# config.py
RISK_MODE = "TOP_DOWN"
MULTIPLIER = 160
FIXED_STAKE = 10.0
MIN_RR_RATIO = 2.0  # 1:2 minimum
```

- Dynamic TP/SL based on market levels
- Structure-based stop placement
- Level-based profit targets

#### **2. Scalping + Wait-Cancel**
```python
RISK_MODE = "SCALPING_WITH_CANCEL"
CANCEL_TIME = 240  # 4 minutes
```

- Fixed percentage targets
- Automatic cancellation at 4min if not profitable
- Aggressive entry/exit

#### **3. Legacy Mode**
```python
RISK_MODE = "LEGACY"
FIXED_TP = 2.0
MAX_LOSS_PER_TRADE = 3.0
```

- Traditional fixed TP/SL
- Percentage-based targets

---

## API Reference

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/register` | POST | Create new user |
| `/api/v1/auth/login` | POST | Get JWT token |
| `/api/v1/auth/me` | GET | Get current user info |

**Example Login:**
```bash
curl -X POST http://localhost:10000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### Bot Control

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/bot/start` | POST | ✅ | Start trading |
| `/api/v1/bot/stop` | POST | ✅ | Stop trading |
| `/api/v1/bot/restart` | POST | ✅ | Restart bot |
| `/api/v1/bot/status` | GET | ✅ | Get bot status |

**Example Start:**
```bash
curl -X POST http://localhost:10000/api/v1/bot/start \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Trading Data

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/trades/active` | GET | ✅ | Active trades |
| `/api/v1/trades/history` | GET | ✅ | Trade history |
| `/api/v1/trades/stats` | GET | ✅ | Statistics |
| `/api/v1/monitor/signals` | GET | ✅ | Recent signals |
| `/api/v1/monitor/performance` | GET | ✅ | Performance metrics |

**Example Stats:**
```bash
curl http://localhost:10000/api/v1/trades/stats \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### WebSocket (Real-time Updates)

Connect to: `ws://localhost:10000/ws/live`

**Events:**
- `bot_status` - Bot state changes
- `signal` - Trading signals detected
- `trade_opened` - New trade executed
- `trade_closed` - Trade completed (P&L)
- `statistics` - Performance updates

**JavaScript Example:**
```javascript
const ws = new WebSocket('ws://localhost:10000/ws/live');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'signal') {
    console.log('Signal:', data.signal, 'Score:', data.score);
  }
  
  if (data.type === 'trade_closed') {
    console.log('P&L:', data.pnl, 'Status:', data.status);
  }
};
```

---

## Deployment

### Deploy to Render (Free Tier)

1. **Push to GitHub:**
```bash
git add .
git commit -m "Deploy to Render"
git push origin main
```

2. **Create Render Service:**
   - Go to [render.com](https://render.com)
   - New → Web Service
   - Connect GitHub repository

3. **Configure:**
```yaml
# Build Command
pip install --upgrade pip && pip install -r requirements.txt

# Start Command
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

4. **Environment Variables:**
```env
ENVIRONMENT=production
BOT_AUTO_START=true
DERIV_API_TOKEN=your_token
DERIV_APP_ID=1089
JWT_SECRET_KEY=your_secret
ADMIN_PASSWORD=secure_password
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_id
```

5. **Deploy** - Takes ~5 minutes

**Your bot will be live at:** `https://your-app.onrender.com`

### Alternative Platforms

<details>
<summary><b>Railway</b></summary>

```bash
npm i -g @railway/cli
railway login
railway init
railway up
```

</details>

<details>
<summary><b>Heroku</b></summary>

```bash
echo "web: uvicorn app.main:app --host 0.0.0.0 --port \$PORT" > Procfile
heroku create your-app-name
git push heroku main
```

</details>

---

## Configuration

### Core Settings (`config.py`)

```python
# Trading Parameters
SYMBOL = "R_25"                    # Deriv synthetic index
MULTIPLIER = 160                   # Contract multiplier
FIXED_STAKE = 10.0                 # Stake per trade ($)

# Risk Management
MAX_TRADES_PER_DAY = 30           # Daily trade cap
MAX_DAILY_LOSS = 10.0             # Max daily loss ($)
MAX_LOSS_PER_TRADE = 3.0          # Max loss per trade ($)
MIN_RR_RATIO = 2.0                # Minimum Risk:Reward ratio

# Strategy Parameters
MOMENTUM_CLOSE_THRESHOLD = 1.5    # ATR multiplier for momentum
WEAK_RETEST_MAX_PCT = 30          # Max retest pullback (%)
MIDDLE_ZONE_PCT = 40              # Avoid middle zone (%)

# Volatility Filters
ATR_MIN_1M = 0.05                 # Minimum 1m ATR
ATR_MAX_1M = 1.5                  # Maximum 1m ATR
ATR_MIN_5M = 0.1                  # Minimum 5m ATR
ATR_MAX_5M = 2.5                  # Maximum 5m ATR
```

### Application Settings (`app/core/settings.py`)

```python
# Server
PORT = 10000
HOST = "0.0.0.0"

# Authentication
ENABLE_AUTHENTICATION = True
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# Bot
BOT_AUTO_START = False            # Auto-start on deployment
```

---

## Monitoring

### Telegram Notifications

**Setup:**

1. Create bot via [@BotFather](https://t.me/BotFather)
2. Get your Chat ID:
   - Message your bot
   - Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Find `"chat":{"id":...}`
3. Add to `.env`:
```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=123456789
```

**Notifications:**
- Signals: `BUY/SELL detected (Score: 8/10)`
- Trades Opened: `Position #12345 opened at $1.50`
- Trades Closed: `Won $1.80 (+20%) in 3m 45s`
- Alerts: `Daily loss limit reached`

### Performance Dashboard

Access via API:

```bash
curl http://localhost:10000/api/v1/monitor/performance \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**
```json
{
  "total_trades": 50,
  "winning_trades": 32,
  "losing_trades": 18,
  "win_rate": 64.0,
  "total_pnl": 15.50,
  "daily_pnl": 3.20,
  "avg_win": 1.85,
  "avg_loss": -2.10,
  "largest_win": 3.50,
  "largest_loss": -3.00,
  "trades_today": 5
}
```

### Logs

```bash
# View recent logs
curl http://localhost:10000/api/v1/monitor/logs?lines=100 \
  -H "Authorization: Bearer YOUR_TOKEN"

# Local file
tail -f trading_bot.log

# Render dashboard
# View in real-time on Render's log viewer
```

---

## Troubleshooting

### Bot Won't Start

**Issue:** `"Bot failed to start"` error

**Solutions:**
1. Verify Deriv API token: `echo $DERIV_API_TOKEN`
2. Check account balance (minimum $50 recommended)
3. Review logs: `/api/v1/monitor/logs`
4. Test connection:
```python
python -c "import config; print('Token valid:', len(config.DERIV_API_TOKEN) > 20)"
```

### No Trading Signals

**Issue:** Bot running but no trades executed

**Common Causes:**
- Weekly/Daily bias not aligned (conflict)
- ATR too high (market too volatile)
- ATR too low (market too quiet)
- Price in middle zone (30-70%)
- No untested levels available

**Debug:**
```bash
curl http://localhost:10000/api/v1/monitor/debug \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Look for rejection reasons:
- `"No clear trend bias - Weekly: BULLISH, Daily: BEARISH"`
- `"Price in middle zone (no nearby levels)"`
- `"No momentum break: Weak momentum (1.2x < 1.5x ATR)"`

### Telegram Not Working

**Issue:** No notifications received

**Solutions:**
1. Verify bot token:
```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

2. Verify chat ID:
```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
```

3. Message bot with `/start`
4. Check logs for Telegram errors

### Authentication Errors

**Issue:** 401 Unauthorized

**Solutions:**
1. Token expired (24h default) → Login again
2. Wrong format → Use: `Bearer YOUR_TOKEN`
3. Invalid credentials → Check username/password
4. JWT secret mismatch → Verify `.env` file

---

## Project Structure

```
deriv-r25-trading-bot/
├── app/                          # FastAPI Application
│   ├── api/                      # REST API Endpoints
│   │   ├── auth.py              # Authentication routes
│   │   ├── bot.py               # Bot control
│   │   ├── trades.py            # Trade management
│   │   └── monitor.py           # Monitoring
│   ├── bot/                      # Bot Core Logic
│   │   ├── runner.py            # Bot lifecycle
│   │   └── state.py             # State management
│   ├── core/                     # Core Utilities
│   │   ├── auth.py              # JWT authentication
│   │   ├── settings.py          # Configuration
│   │   └── logging.py           # Logging setup
│   ├── schemas/                  # Pydantic Models
│   │   ├── auth.py              # Auth schemas
│   │   └── trades.py            # Trade schemas
│   ├── ws/                       # WebSocket
│   │   └── live.py              # Real-time updates
│   └── main.py                   # FastAPI app entry
│
├── config.py                     # Trading configuration
├── data_fetcher.py              # Multi-timeframe data (1w→1m)
├── strategy.py                  # Top-Down strategy logic
├── trade_engine.py              # Trade execution
├── risk_manager.py              # Risk management
├── indicators.py                # Technical indicators
├── telegram_notifier.py         # Telegram integration
├── utils.py                     # Helper functions
├── main.py                      # Main trading loop
│
├── requirements.txt             # Dependencies
├── .env                         # Environment variables
├── .env.example                 # Template
├── render.yaml                  # Render config
└── README.md                    # This file
```

---

## License

MIT License - See [LICENSE](LICENSE) file for details