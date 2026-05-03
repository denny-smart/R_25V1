"""
Rise/Fall bot configuration for R_25 Support & Resistance strategy.

Entry model:
  - Analyse 1-minute OHLCV candles to locate support and resistance zones.
  - Wait for price to enter a zone.
  - Require a confirmation candle that closes INSIDE or bouncing OFF the zone.
  - Enter RISE (CALL) at support, FALL (PUT) at resistance.
  - Contract duration: 2 minutes.
"""

import os

# ==================== SYMBOLS ====================
# Strategy is R_25 only.
RF_SYMBOLS = ["R_25"]
RF_LEGACY_SYMBOL_ALIASES = {"R_25": "R_25"}
RF_SUPPORTED_SYMBOLS = tuple(RF_SYMBOLS) + tuple(RF_LEGACY_SYMBOL_ALIASES.keys())
SYMBOLS = RF_SYMBOLS
RF_BLOCKED_SYMBOLS = set()

# ==================== CANDLE / TIMEFRAME ====================
# Primary analysis timeframe for the bot (minutes per candle).
RF_CANDLE_INTERVAL_MINUTES = 1

# ==================== SUPPORT & RESISTANCE DETECTION ====================
# How many 1-minute candles to load for S&R calculation.
RF_SR_CANDLE_COUNT = 100

# A price level is a swing-high/low pivot if it is the highest/lowest
# close over the surrounding RF_SR_PIVOT_WINDOW candles on each side.
RF_SR_PIVOT_WINDOW = 5

# Two pivot levels that are within RF_SR_MERGE_PCT % of each other
# are merged into a single zone.
RF_SR_MERGE_PCT = 0.10          # 0.10 %

# A zone is considered "touched" (active) when the candle's high or low
# comes within this many pips/points of the zone's midpoint.
RF_SR_ZONE_TOUCH_BUFFER_PCT = 0.05   # 0.05 % of price

# Maximum number of S&R zones retained at runtime (strongest / most recent).
RF_SR_MAX_ZONES = 10

# Minimum number of touches a zone must have had to be considered strong.
RF_SR_MIN_TOUCHES = 2

# ==================== CONFIRMATION CANDLE RULES ====================
# The confirmation candle must close within the zone OR show a clear
# rejection wick (hammer / shooting-star pattern).
#
# Rejection wick ratio: wick must be at least this multiple of the body.
RF_CONFIRM_WICK_RATIO = 2.0

# The confirmation candle body must be at most this % of the zone width
# for a "pin-bar" confirmation.  Set 0 to disable body-size filter.
RF_CONFIRM_MAX_BODY_PCT_OF_ZONE = 150.0

# Number of candles to look back for the confirmation pattern
# (1 = only the most recently closed candle).
RF_CONFIRM_LOOKBACK = 1

# ==================== CONTRACT PARAMETERS ====================
RF_DEFAULT_STAKE  = 1.00
RF_CONTRACT_DURATION  = 2
RF_DEFAULT_DURATION   = RF_CONTRACT_DURATION
RF_DURATION_UNIT      = "m"          # minutes
RF_DURATION_UNIT_LABEL = "minutes"

# ==================== RISK MANAGEMENT ====================
RF_MAX_CONCURRENT_PER_SYMBOL = 1
RF_MAX_CONCURRENT_TOTAL      = 1
RF_MAX_CONCURRENT_TRADES     = 1

# No artificial cooldowns — each signal is already gated by the zone-touch
# and confirmation-candle logic.
RF_COOLDOWN_SECONDS        = 0
RF_GLOBAL_COOLDOWN_SECONDS = 0

# Cap entries to 20 per day.
RF_MAX_TRADES_PER_DAY          = 20
RF_DAILY_LOSS_LIMIT_MULTIPLIER = 0.0

RF_PENDING_TIMEOUT_SECONDS  = 60
RF_MAX_CONSECUTIVE_LOSSES   = 3
RF_LOSS_COOLDOWN_SECONDS    = 15 * 60   # 15 minutes after 3 straight losses
RF_LOSS_STREAK_LIMIT        = RF_MAX_CONSECUTIVE_LOSSES
RF_LOSS_STREAK_COOLDOWN_MINUTES = 15
RF_SESSION_MAX_LOSSES       = 6
RF_SESSION_RESET_MODE       = "daily"

RF_MAX_STAKE = 100.0

# ==================== LOGGING ====================
RF_LOG_FILE  = "logs/risefall/risefall_bot.log"
RF_LOG_LEVEL = "INFO"

# ==================== DB WRITE RETRY ====================
RF_DB_WRITE_MAX_RETRIES = 3
RF_DB_WRITE_RETRY_DELAY = 2

# ==================== WEBSOCKET ====================
RF_WS_URL     = "wss://ws.derivws.com/websockets/v3"
RF_WS_TIMEOUT = 30
RF_APP_ID     = os.getenv("DERIV_APP_ID", "1089")

# ==================== BOT LOOP ====================
# Scan every 60 s so each new 1-minute candle is inspected once.
RF_SCAN_INTERVAL = 60

# ==================== CROSS-PROCESS LOCK ====================
RF_ENFORCE_DB_LOCK        = True
RF_DB_LOCK_TTL_SECONDS    = 900
RF_GRACEFUL_SHUTDOWN_TIMEOUT = 15