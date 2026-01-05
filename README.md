# Deriv Multi-Asset Trading Bot

**Professional automated trading bot for Deriv's volatility indices (R_25, R_50, R_75, etc.) using top-down market structure analysis.**

Live Demo: https://r-25v1.onrender.com/docs/

---

## Key Features

- **Multi-Asset Scanning** - Simultaneous analysis of multiple indices (R_25, R_50, R_75, etc.)
- **Global Risk Control** - Strict "1 active trade" limit across ALL assets to prevent over-leverage
- **Top-Down Strategy** - Weekly/Daily trend analysis with 1m/5m execution
- **Smart Startup Recovery** - Automatically detects and manages existing open positions on restart
- **Dynamic Risk Management** - Structure-based stops and level-based targets
- **Enhanced Rich Notifications** - Real-time signals with strength bars, ROI tracking, and status badges
- **REST API + WebSocket** - Full control and real-time monitoring
- **JWT Authentication** - Secure access control
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
3. [Development Rules & Best Practices](#development-rules--best-practices)
4. [Risk Management](#risk-management)
5. [API Reference](#api-reference)
6. [Deployment](#deployment)
7. [Configuration](#configuration)
8. [Monitoring](#monitoring)
9. [Troubleshooting](#troubleshooting)
10. [Development Commands Reference](#development-commands-reference)
11. [Project Structure](#project-structure)

---

## Quick Start

### 1. Prerequisites

**Required:**
- **Python 3.10+** (tested with 3.10, 3.11, 3.13)
- **Deriv Account** with API token ([Get one here](https://app.deriv.com/account/api-token))
- **Supabase Account** for authentication ([Sign up free](https://supabase.com))

**Optional:**
- **Telegram Bot** for notifications ([create via @BotFather](https://t.me/BotFather))

**System Requirements:**
- Minimum 512MB RAM
- Stable internet connection
- Works on Windows, Linux, macOS

### 2. Installation

```bash
# Clone repository
git clone https://github.com/yourusername/deriv-r25-trading-bot.git
cd deriv-r25-trading-bot

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Supabase Setup

#### Step 1: Create Supabase Project

1. Go to [Supabase Dashboard](https://app.supabase.com)
2. Click **New Project**
3. Fill in project details and create
4. Save your **Project URL** and **API Keys**

#### Step 2: Run Database Setup

1. In Supabase Dashboard, go to **SQL Editor**
2. Click **New Query**
3. Copy contents of `supabase_setup.sql` and paste
4. Click **Run** to execute

This creates:
- `profiles` table for user management
- Row Level Security policies
- Trigger for new user signup
- Admin approval workflow

#### Step 3: Get API Keys

In your Supabase project:
1. Go to **Settings** → **API**
2. Copy **Project URL**
3. Copy **anon/public key** (for client operations)
4. Copy **service_role key** (for admin operations, **keep secret!**)

### 4. Environment Configuration

Create `.env` file in project root:

```env
# ============================================================================
# DERIV API CONFIGURATION (Required)
# ============================================================================
DERIV_API_TOKEN=your_deriv_api_token_here
DERIV_APP_ID=1089

# Get your token: https://app.deriv.com/account/api-token
# Make sure to enable trading permissions

# ============================================================================
# SUPABASE CONFIGURATION (Required)
# ============================================================================
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
SUPABASE_ANON_KEY=your_anon_key_here

# Find these in: Supabase Dashboard → Settings → API

# ============================================================================
# AUTHENTICATION (Required)
# ============================================================================
ENABLE_AUTHENTICATION=true
INITIAL_ADMIN_EMAIL=your.email@example.com

# The email you'll use to sign up as the first admin

# ============================================================================
# TELEGRAM NOTIFICATIONS (Optional)
# ============================================================================
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789

# Get token: Message @BotFather on Telegram, use /newbot
# Get chat ID: Message your bot, then visit:
# https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates

# ============================================================================
# APPLICATION SETTINGS
# ============================================================================
ENVIRONMENT=development
BOT_AUTO_START=false
PORT=10000
DEBUG=false

# ============================================================================
# OPTIONAL SETTINGS (Use defaults if unsure)
# ============================================================================
LOG_LEVEL=INFO
WS_REQUIRE_AUTH=false
RATE_LIMIT_ENABLED=true
```

**Security Notes:**
- Never commit `.env` to git (already in `.gitignore`)
- Keep `SUPABASE_SERVICE_ROLE_KEY` secret - it bypasses Row Level Security
- Use strong, unique values for production

### 5. Create Admin User

#### Option A: First User Signup

1. Start the server (see step 6)
2. Go to `http://localhost:10000/docs`
3. Use `/api/v1/auth/register` to create an account with your `INITIAL_ADMIN_EMAIL`
4. The account will be created but **not approved** yet

#### Option B: Promote Existing User to Admin

```bash
# If user already exists, promote them to admin
python create_admin.py your.email@example.com

# Follow the prompts to confirm
```

This script:
- Searches for the user by email
- Sets `role='admin'` and `is_approved=true`
- Grants full access to the API

### 6. Run the Bot

```bash
# Start server
uvicorn app.main:app --host 0.0.0.0 --port 10000 --reload

# Access at:
# • API Docs: http://localhost:10000/docs
# • Dashboard: http://localhost:10000/
# • Health: http://localhost:10000/health
```

### 7. Control via API

**First, Login:**

```bash
# Login with your Supabase account
curl -X POST http://localhost:10000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "your.email@example.com", "password": "your_password"}'

# Response includes access_token
```

**Then, Control the Bot:**

```bash
# Start bot (use token from login)
curl -X POST http://localhost:10000/api/v1/bot/start \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Get status
curl http://localhost:10000/api/v1/bot/status \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Stop bot
curl -X POST http://localhost:10000/api/v1/bot/stop \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
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

## Development Rules & Best Practices

### Code Organization

The project follows a clear separation of concerns:

**API Layer** (`app/api/`)
- RESTful endpoints with FastAPI
- Request validation via Pydantic schemas
- Authentication middleware using Supabase
- WebSocket for real-time updates

**Bot Core** (`app/bot/`)
- Trading logic and strategy execution
- Multi-asset scanning and monitoring
- State management and lifecycle control
- Independent from API layer (can run standalone)

**Data Layer**
- `data_fetcher.py` - Multi-timeframe data retrieval from Deriv
- `indicators.py` - Technical analysis calculations
- `utils.py` - Shared helper functions

**Strategy & Risk**
- `strategy.py` - Top-down market structure analysis
- `risk_manager.py` - Global position tracking, daily limits, cooldowns
- `trade_engine.py` - Contract execution and monitoring

### Configuration Management

**Environment-Specific Settings:**
- Development: Use `.env` file with `ENVIRONMENT=development`
- Production: Set environment variables in hosting platform (Render, Railway, etc.)
- Never hardcode sensitive values

**Trading Configuration** (`config.py`)
```python
# Multi-asset settings
SYMBOLS = ["R_25", "R_50", "R_75"]  # Assets to monitor
MAX_CONCURRENT_TRADES = 1            # Global limit across all assets

# Risk management
MAX_DAILY_LOSS = 10.0                # Global daily loss limit ($)
MIN_RR_RATIO = 2.0                   # Minimum risk-to-reward ratio

# Strategy mode
USE_TOPDOWN_STRATEGY = True          # Top-Down vs Legacy
RISK_MODE = "TOP_DOWN"               # Dynamic TP/SL based on levels
```

**Validation** - Always validate before deploying:
```bash
python config.py  # Runs full config validation
```

### Testing Procedures

**1. Test Deriv API Connection**
```bash
python verify_api.py
```
Expected output: Connection successful, account balance displayed

**2. Test Telegram Notifications**
```bash
python test_telegram.py
```
Expected: Message sent to your Telegram chat

**3. Test API Endpoints**
```bash
# Health check
curl http://localhost:10000/health

# Should return: {"status": "healthy", "bot_status": "stopped"}
```

**4. Test Supabase Connection**
```bash
# Start server and check logs for:
# "✅ Supabase client initialized"
```

**5. Integration Testing**
- Use Swagger UI at `http://localhost:10000/docs`
- Test authentication flow: Register → Login → Access protected endpoints
- Test bot lifecycle: Start → Monitor status → Stop

### Development Workflow

**1. Before Making Changes:**
```bash
# Pull latest changes
git pull origin main

# Create feature branch
git checkout -b feature/your-feature-name

# Activate venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
```

**2. Making Changes:**
- Update code in appropriate module
- Update `config.py` if adding new parameters
- Update tests if changing core logic
- Test locally before committing

**3. Before Committing:**
```bash
# Validate configuration
python config.py

# Test critical paths
python verify_api.py
python test_telegram.py

# Check for syntax errors
python -m py_compile app/main.py
```

**4. Deployment Checklist:**
- [ ] All environment variables set in production
- [ ] Supabase database schema up to date
- [ ] Admin user created and approved
- [ ] Deriv API token has trading permissions
- [ ] Telegram bot configured (if using)
- [ ] `BOT_AUTO_START` set appropriately
- [ ] Log level set to `INFO` or `WARNING` in production

### Common Development Tasks

**Add a New Trading Symbol:**
```python
# In config.py
SYMBOLS = ["R_25", "R_50", "R_75", "NEW_SYMBOL"]

ASSET_CONFIG = {
    "NEW_SYMBOL": {
        "multiplier": 80,
        "description": "Your New Asset",
        "tick_size": 0.01
    }
}
```

**Adjust Risk Parameters:**
```python
# In config.py
MAX_DAILY_LOSS = 15.0      # Increase daily loss limit
MIN_RR_RATIO = 2.5         # Require better risk/reward
MAX_TRADES_PER_DAY = 50    # Allow more trades
```

**Change Strategy Mode:**
```python
# In config.py
RISK_MODE = "TOP_DOWN"     # Use dynamic TP/SL based on levels
# or
RISK_MODE = "FIXED"        # Use fixed percentage TP/SL
```

### Troubleshooting Development Issues

**"Module not found" errors:**
```bash
# Ensure venv is activated and dependencies installed
pip install -r requirements.txt
```

**Config validation fails:**
- Check all required env vars are set in `.env`
- Verify `SYMBOLS` list matches `ASSET_CONFIG` keys
- Ensure `MIN_RR_RATIO == TOPDOWN_MIN_RR_RATIO`

**Bot won't start locally:**
- Verify Deriv API token is valid
- Check account has sufficient balance (min $50 recommended)
- Ensure no firewall blocking WebSocket connections

---

## Risk Management

### Multi-Layer Protection System

### Multi-Layer Protection System

| Protection Layer | Rule | Purpose |
|------------------|------|---------|
| **Global Position Lock** | 1 active trade (ALL assets) | **Prevents over-leveraging across portfolio** |
| **Daily Loss Limit** | -$10.00 max (Global) | Preserves capital |
| **Trade Frequency** | Max 30 trades/day | Prevents overtrading |
| **Consecutive Loss** | 3 losses → cooldown | Stops bleed during drawdowns |
| **Smart Recovery** | Auto-detect open trades | Prevents double-entry on restart |
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
SYMBOLS = ["R_25", "R_50", "R_75"] # Active assets
SYMBOL = "R_25"                    # Default fallback
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

The bot sends **rich, visual notifications** to keep you informed instantly:

```text
🟢 SIGNAL DETECTED: R_25
━━━━━━━━━━━━━━━━━━━━
📍 Direction: BUY
📊 Strength: ▮▮▮▮▯ (8.0)
📉 RSI: 55.4 | ADX: 28.1

✅ TRADE WON: R_25
━━━━━━━━━━━━━━━━━━━━
💰 Net Result: $1.80
📈 ROI: +20.0%
━━━━━━━━━━━━━━━━━━━━
⏱️ Duration: 3m 45s
```

- **Signals**: Real-time detection with strength bars
- **Trades**: Entry price, stake, and projected targets
- **Results**: P&L, ROI %, and duration metrics
- **Alerts**: Daily loss limit and system warnings

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

1. **Check Deriv API Token:**
   ```bash
   # Verify token is set
   python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('Token:', os.getenv('DERIV_API_TOKEN')[:10] + '...')"
   ```

2. **Verify Account Balance:**
   - Login to Deriv account
   - Check balance is at least $50 (recommended)
   - Ensure account is not locked

3. **Test API Connection:**
   ```bash
   python verify_api.py
   ```
   Expected: Connection successful, balance displayed

4. **Check Logs:**
   ```bash
   # View recent logs
   curl http://localhost:10000/api/v1/monitor/logs?lines=100 \
     -H "Authorization: Bearer YOUR_TOKEN"
   
   # Or check file directly
   tail -f trading_bot.log
   ```

### Supabase Connection Errors

**Issue:** `"Supabase client initialization failed"`

**Solutions:**

1. **Verify Environment Variables:**
   ```bash
   # Check all Supabase vars are set
   python -c "from app.core.settings import settings; print('URL:', settings.SUPABASE_URL); print('Keys:', 'OK' if settings.SUPABASE_SERVICE_ROLE_KEY else 'MISSING')"
   ```

2. **Test Supabase Connection:**
   - Start server and watch logs for "✅ Supabase client initialized"
   - If error, verify URL format: `https://xxx.supabase.co`
   - Ensure service role key is complete (very long string starting with `eyJ...`)

3. **Check Supabase Project Status:**
   - Go to Supabase Dashboard
   - Verify project is active (not paused)
   - Check if database is healthy in Settings → Database

**Issue:** `"No user found with email"`

**Solutions:**
- Ensure user has signed up first via `/api/v1/auth/register`
- Check email spelling matches exactly
- Verify `profiles` table exists in Supabase (run `supabase_setup.sql` if not)

### Authentication Errors

**Issue:** 401 Unauthorized when accessing protected endpoints

**Solutions:**

1. **Token Expired:**
   - Tokens expire after 1 hour (Supabase default)
   - Login again to get new token
   
2. **Wrong Token Format:**
   ```bash
   # Correct format:
   Authorization: Bearer eyJ...actual_token_here...xyz
   
   # NOT: Authorization: YOUR_TOKEN
   ```

3. **User Not Approved:**
   - Check user status:
     ```sql
     -- In Supabase SQL Editor
     SELECT email, role, is_approved FROM profiles;
     ```
   - Promote to admin if needed:
     ```bash
     python create_admin.py user@example.com
     ```

### No Trading Signals

**Issue:** Bot running but no trades executed

**Common Causes:**

1. **Weekly/Daily Bias Not Aligned:**
   - Check debug logs for: `"No clear trend bias - Weekly: BULLISH, Daily: BEARISH"`
   - Strategy requires both timeframes aligned
   - Market may be in consolidation

2. **ATR Out of Range:**
   ```python
   # In config.py, adjust if needed:
   ATR_MIN_1M = 0.05  # Lower if market too quiet
   ATR_MAX_1M = 2.0   # Raise if market very volatile
   ```

3. **Price in Middle Zone:**
   - Bot avoids trading in middle 40% between levels
   - Wait for price to reach key support/resistance

4. **No Untested Levels Available:**
   - Bot targets untested levels for TP
   - If none exist, it won't trade
   - Check: `curl http://localhost:10000/api/v1/monitor/debug`

**Debug Command:**
```bash
curl http://localhost:10000/api/v1/monitor/debug \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Look for rejection reasons:
- `"No momentum break: Weak momentum (1.2x < 1.5x ATR)"`
- `"Price in middle zone (no nearby levels)"`
- `"Insufficient risk:reward ratio (1.5:1 < 2.0:1 minimum)"`

### Telegram Not Working

**Issue:** No notifications received

**Solutions:**

1. **Verify Bot Token:**
   ```bash
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
   ```
   Expected: Bot information JSON

2. **Verify Chat ID:**
   ```bash
   # Message your bot, then check:
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
   ```
   Look for: `"chat":{"id":123456789}`

3. **Test Notification:**
   ```bash
   python test_telegram.py
   ```
   Should receive test message

4. **Check Bot Was Started:**
   - Message your bot with `/start`
   - Bots can't message users who haven't started them

5. **Check Environment Variables:**
   ```bash
   # Verify both are set
   echo $TELEGRAM_BOT_TOKEN
   echo $TELEGRAM_CHAT_ID
   ```

### Deployment Issues (Render/Railway)

**Issue:** Build fails on deployment

**Solutions:**

1. **Python Version Mismatch:**
   - Render uses Python 3.11 by default
   - Add `runtime.txt` if needed:
     ```
     python-3.11.0
     ```

2. **Missing Environment Variables:**
   - Go to Dashboard → Environment
   - Verify ALL required vars are set (see `.env` template)
   - Check for typos in variable names

3. **Build Command Errors:**
   ```bash
   # Correct build command:
   pip install --upgrade pip && pip install -r requirements.txt
   ```

**Issue:** Bot starts but immediately stops

**Solutions:**

1. **Check Global Position Lock:**
   - If you restart while a trade is open, bot detects and locks
   - Check logs for: "Existing position detected, locking global position"
   - This is normal - wait for trade to close

2. **Daily Loss Limit Hit:**
   - Check: `curl http://localhost:10000/api/v1/trades/stats`
   - If `daily_pnl` <= `-MAX_DAILY_LOSS`, bot auto-stops
   - Wait for next day or adjust `MAX_DAILY_LOSS` in config

3. **Deriv API Issues:**
   - Verify API token permissions include trading
   - Check Deriv's system status
   - Test with `python verify_api.py`

### Environment Variable Issues

**Issue:** `"API_TOKEN not set"` or similar errors

**Solutions:**

1. **File Not Loaded:**
   ```bash
   # Ensure .env file exists
   ls -la .env
   
   # Check it's being loaded
   python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('Loaded:', 'DERIV_API_TOKEN' in os.environ)"
   ```

2. **Variable Name Mismatch:**
   - Use `DERIV_API_TOKEN` (not `API_TOKEN` alone)
   - Use `DERIV_APP_ID` (not `APP_ID` alone)
   - Check `config.py` for fallback logic

3. **Deployment Platform:**
   - Render/Railway use dashboard for env vars, not `.env` file
   - Set each variable individually in platform dashboard

### Port Already in Use

**Issue:** `"Address already in use"` error

**Solutions:**

```bash
# Windows - Find and kill process on port 10000
netstat -ano | findstr :10000
taskkill /PID <process_id> /F

# Linux/macOS
lsof -ti:10000 | xargs kill -9

# Or use different port
uvicorn app.main:app --port 8000
```

### Database/Supabase Schema Issues

**Issue:** `"relation 'profiles' does not exist"`

**Solutions:**
1. Run database setup:
   - Go to Supabase Dashboard → SQL Editor
   - Copy and paste `supabase_setup.sql` contents
   - Execute the query

2. Verify table created:
   ```sql
   -- In Supabase SQL Editor
   SELECT * FROM profiles;
   ```

3. If table exists but still errors:
   - Check RLS policies are correct
   - Verify trigger is active: `SELECT * FROM pg_trigger WHERE tgname = 'on_auth_user_created';`

---

## Development Commands Reference

Quick reference for common operations:

### Configuration & Validation
```bash
# Validate trading configuration
python config.py

# Test Deriv API connection
python verify_api.py

# Test Telegram bot
python test_telegram.py

# Check settings loading
python test_settings.py
```

### Server Operations
```bash
# Start development server
uvicorn app.main:app --reload --port 10000

# Start with specific host
uvicorn app.main:app --host 0.0.0.0 --port 10000

# Production mode (no reload)
uvicorn app.main:app --host 0.0.0.0 --port 10000 --workers 1
```

### User Management
```bash
# Create/promote admin user
python create_admin.py your.email@example.com

# Check user status (Supabase SQL Editor)
SELECT email, role, is_approved FROM profiles;
```

### Monitoring & Debugging
```bash
# Health check
curl http://localhost:10000/health

# Bot status
curl http://localhost:10000/api/v1/bot/status \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get trading statistics
curl http://localhost:10000/api/v1/trades/stats \
  -H "Authorization: Bearer YOUR_TOKEN"

# View logs via API
curl http://localhost:10000/api/v1/monitor/logs?lines=100 \
  -H "Authorization: Bearer YOUR_TOKEN"

# View log file directly
tail -f trading_bot.log

# Debug signals
curl http://localhost:10000/api/v1/monitor/debug \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Bot Control
```bash
# Login first
curl -X POST http://localhost:10000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "your@email.com", "password": "your_password"}'

# Start bot
curl -X POST http://localhost:10000/api/v1/bot/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# Stop bot
curl -X POST http://localhost:10000/api/v1/bot/stop \
  -H "Authorization: Bearer YOUR_TOKEN"

# Restart bot
curl -X POST http://localhost:10000/api/v1/bot/restart \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Git Workflow
```bash
# Create feature branch
git checkout -b feature/your-feature

# Commit changes
git add .
git commit -m "Description of changes"

# Push to remote
git push origin feature/your-feature

# Pull latest
git pull origin main
```

### Kill Process on Port (if needed)
```bash
# Windows
netstat -ano | findstr :10000
taskkill /PID <process_id> /F

# Linux/macOS
lsof -ti:10000 | xargs kill -9
```

---

## Project Structure

```
deriv-r25-trading-bot/
├── app/                          # FastAPI application
│   ├── api/                      # REST API endpoints
│   │   ├── __init__.py
│   │   ├── auth.py              # Supabase auth routes (register, login, profile)
│   │   ├── bot.py               # Bot control (start, stop, restart, status)
│   │   ├── trades.py            # Trade history, active trades, statistics
│   │   ├── monitor.py           # Performance monitoring, logs, debug info
│   │   └── config.py            # Configuration management API
│   │
│   ├── bot/                      # Core bot logic
│   │   ├── __init__.py
│   │   ├── runner.py            # Bot lifecycle, multi-asset scanning loop
│   │   ├── state.py             # Global bot state management
│   │   ├── events.py            # Event emission system
│   │   └── telegram_bridge.py   # Bridge between bot and Telegram notifier
│   │
│   ├── core/                     # Core utilities
│   │   ├── __init__.py
│   │   ├── auth.py              # Supabase authentication helpers
│   │   ├── settings.py          # Pydantic settings (from .env)
│   │   ├── supabase.py          # Supabase client initialization
│   │   ├── logging.py           # Structured logging configuration
│   │   └── serializers.py       # JSON serialization helpers
│   │
│   ├── schemas/                  # Pydantic models for validation
│   │   ├── __init__.py
│   │   ├── auth.py              # User, login, register schemas
│   │   ├── bot.py               # Bot status, control schemas
│   │   ├── trades.py            # Trade, signal, statistics schemas
│   │   └── common.py            # Shared response models
│   │
│   ├── ws/                       # WebSocket server
│   │   ├── __init__.py
│   │   └── live.py              # Real-time updates (signals, trades, status)
│   │
│   └── main.py                   # FastAPI app initialization, CORS, routes
│
├── tests/                        # Test suite
│   └── test_fixes.py            # Integration tests
│
├── config.py                     # Trading configuration (MAIN CONFIG FILE)
│                                 # - Multi-asset settings (SYMBOLS, ASSET_CONFIG)
│                                 # - Risk parameters (MAX_DAILY_LOSS, MIN_RR_RATIO)
│                                 # - Strategy settings (TOP_DOWN, FIXED modes)
│                                 # - Validation functions
│
├── data_fetcher.py              # Multi-timeframe data fetching
│                                 # - fetch_all_timeframes(): 1w, 1d, 4h, 1h, 5m, 1m
│                                 # - Deriv WebSocket candle streaming
│                                 # - Retry logic and error handling
│
├── strategy.py                  # Top-down market structure analysis
│                                 # - Weekly/Daily bias determination
│                                 # - Level detection (tested, untested, minor)
│                                 # - Entry signal generation (momentum + retest)
│                                 # - Dynamic TP/SL calculation
│
├── trade_engine.py              # Trade execution and monitoring
│                                 # - Contract creation (MULTUP/MULTDOWN)
│                                 # - TP/SL monitoring loop
│                                 # - P&L tracking and trade closure
│                                 # - Portfolio query for startup recovery
│
├── risk_manager.py              # Risk management engine
│                                 # - Global position lock (1 trade max)
│                                 # - Daily loss tracking
│                                 # - Trade frequency limits
│                                 # - Consecutive loss cooldown
│                                 # - Smart startup recovery
│
├── indicators.py                # Technical indicators
│                                 # - RSI, ADX, ATR calculations
│                                 # - Moving averages (SMA, EMA)
│                                 # - Swing high/low detection
│
├── telegram_notifier.py         # Telegram notifications
│                                 # - Rich formatted messages
│                                 # - Signal alerts with strength bars
│                                 # - Trade results with ROI tracking
│                                 # - System status updates
│
├── utils.py                     # Helper functions
│                                 # - Logging utilities
│                                 # - Date/time formatting
│                                 # - Price formatting
│
├── create_admin.py              # Admin user creation script
│                                 # Usage: python create_admin.py user@example.com
│
├── verify_api.py                # Deriv API connection test
├── test_telegram.py             # Telegram bot test
├── test_settings.py             # Settings validation test
│
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables (NOT in git)
├── .env.example                 # Environment template (to be created)
├── .gitignore                   # Git ignore rules
├── render.yaml                  # Render deployment config
├── supabase_setup.sql           # Supabase database schema
└── README.md                    # This file
```

### Key Files Explained

**Configuration Files**
- `config.py` - **Primary trading configuration**. All strategy, risk, and asset settings. Run `python config.py` to validate.
- `.env` - **Secrets and environment-specific settings**. Never commit to git.
- `app/core/settings.py` - **FastAPI application settings**. Loads from `.env` via Pydantic.

**Entry Points**
- `app/main.py` - **FastAPI server**. Start with `uvicorn app.main:app`
- `main.py` - **Standalone bot** (legacy). Not used when running via FastAPI.

**Core Trading Logic Flow**
1. `app/bot/runner.py` - Monitors all assets, coordinates scanning
2. `data_fetcher.py` - Fetches multi-timeframe data for each asset
3. `strategy.py` - Analyzes data, generates signals
4. `risk_manager.py` - Validates signal against risk rules
5. `trade_engine.py` - Executes approved trades
6. `telegram_notifier.py` - Sends notifications

**Database**
- Supabase (cloud) - User authentication and profiles
- No local database required

---

## License

MIT License - See [LICENSE](LICENSE) file for details