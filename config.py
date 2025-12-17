"""
Configuration Settings for Deriv R_25 Multipliers Trading Bot
Realistic Scalping Settings - $2.5 stake, 0.2% SL / 0.5% TP
Loads API credentials from .env file
config.py - OPTIMIZED FOR SCALPING
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==================== API CREDENTIALS ====================
# These are loaded from .env file for security
API_TOKEN = os.getenv("API_TOKEN")
APP_ID = os.getenv("APP_ID", "1089")  # Default to public app ID if not set

# For backward compatibility, also check old names
DERIV_API_TOKEN = API_TOKEN if API_TOKEN else os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = APP_ID if APP_ID and APP_ID != "1089" else os.getenv("DERIV_APP_ID", "1089")

# Validate that API token is set
if not DERIV_API_TOKEN or DERIV_API_TOKEN == "your_api_token_here":
    raise ValueError(
        "API_TOKEN not set! Please add your API token to .env file.\n"
        "Your .env file should contain:\n"
        "APP_ID=1089\n"
        "API_TOKEN=your_actual_token_here"
    )

# ==================== TRADING PARAMETERS ====================
SYMBOL = "R_25"                    # Volatility 25 Index
MARKET = "synthetic_index"         # Market type
CONTRACT_TYPE = "MULTUP"           # Multiplier Up (Buy)
CONTRACT_TYPE_DOWN = "MULTDOWN"    # Multiplier Down (Sell)

# ==================== RISK MANAGEMENT ====================
# OPTIMIZED FOR REALISTIC SCALPING
FIXED_STAKE = 2.5                  # Reduced stake for tighter stops (USD)
MULTIPLIER = 160                   # Conservative multiplier (160x)
TAKE_PROFIT_PERCENT = 0.5          # Take profit 0.5% = $2.00 profit
STOP_LOSS_PERCENT = 0.2            # Stop loss 0.2% = $0.80 loss
MAX_LOSS_PER_TRADE = 0.8           # Maximum loss per trade (USD)
COOLDOWN_SECONDS = 120             # Wait time between trades (2 minutes)
MAX_TRADES_PER_DAY = 50            # Maximum trades allowed per day
MAX_DAILY_LOSS = 30.0              # Stop trading if daily loss exceeds this

# Valid multipliers for R_25 (for reference)
VALID_MULTIPLIERS = [160, 400, 800, 1200, 1600]

# ==================== TRADE CALCULATIONS ====================
# These are calculated automatically - DO NOT MODIFY
# Max Profit: 0.5% × $2.5 × 160 = $2.00
# Max Loss: 0.2% × $2.5 × 160 = $0.80
# Risk-to-Reward Ratio: 1:2.5

# ==================== DATA FETCHING ====================
# Increased candles to support SMA(100) calculation
CANDLES_1M = 150                   # Number of 1-minute candles to fetch
CANDLES_5M = 120                   # Number of 5-minute candles to fetch
MAX_RETRIES = 3                    # Maximum retry attempts for API calls
RETRY_DELAY = 2                    # Seconds to wait between retries

# ==================== STRATEGY PARAMETERS ====================
# ATR Validation Ranges
ATR_MIN_1M = 0.05                 # Minimum 1m ATR
ATR_MAX_1M = 1.5                  # Maximum 1m ATR
ATR_MIN_5M = 0.10                 # Minimum 5m ATR
ATR_MAX_5M = 2.5                  # Maximum 5m ATR

# RSI Thresholds - Optimized for scalping
RSI_BUY_THRESHOLD = 55            # Lower threshold for more signals
RSI_SELL_THRESHOLD = 45           # Higher threshold for more signals

# ADX Threshold
ADX_THRESHOLD = 18                # Minimum ADX for trend confirmation

# Moving Averages
SMA_PERIOD = 100                  # Simple Moving Average period
EMA_PERIOD = 20                   # Exponential Moving Average period

# Signal Scoring - Relaxed for scalping
MINIMUM_SIGNAL_SCORE = 5          # Lower minimum score for more opportunities

# Filters
VOLATILITY_SPIKE_MULTIPLIER = 2.5  # ATR multiplier for spike detection
WEAK_CANDLE_MULTIPLIER = 0.3      # ATR multiplier for weak candle filter

# ==================== TRADE MONITORING ====================
MAX_TRADE_DURATION = 1800          # Maximum trade duration (30 minutes for scalping)
MONITOR_INTERVAL = 3               # Check trade status every 3 seconds (faster for scalping)

# ==================== LOGGING ====================
LOG_FILE = "trading_bot.log"
LOG_LEVEL = "DEBUG"                # DEBUG level for detailed monitoring

# ==================== WEBSOCKET ====================
WS_URL = "wss://ws.derivws.com/websockets/v3"
WS_TIMEOUT = 30                    # WebSocket connection timeout

# ==================== VALIDATION ====================
def validate_config():
    """Validate configuration settings"""
    errors = []
    
    # Check API credentials
    if not DERIV_API_TOKEN:
        errors.append("API_TOKEN is not set in .env file")
    
    # Validate risk parameters
    if FIXED_STAKE <= 0:
        errors.append("FIXED_STAKE must be positive")
    if TAKE_PROFIT_PERCENT <= 0:
        errors.append("TAKE_PROFIT_PERCENT must be positive")
    if STOP_LOSS_PERCENT <= 0:
        errors.append("STOP_LOSS_PERCENT must be positive")
    if MULTIPLIER not in VALID_MULTIPLIERS:
        errors.append(f"MULTIPLIER must be one of {VALID_MULTIPLIERS}")
    
    # Validate calculated profit/loss
    calculated_profit = TAKE_PROFIT_PERCENT / 100 * FIXED_STAKE * MULTIPLIER
    calculated_loss = STOP_LOSS_PERCENT / 100 * FIXED_STAKE * MULTIPLIER
    
    if calculated_loss > MAX_LOSS_PER_TRADE * 1.1:  # 10% tolerance
        errors.append(
            f"Calculated stop loss (${calculated_loss:.2f}) exceeds "
            f"MAX_LOSS_PER_TRADE (${MAX_LOSS_PER_TRADE})"
        )
    
    # Validate thresholds
    if not (0 < RSI_BUY_THRESHOLD < 100):
        errors.append("RSI_BUY_THRESHOLD must be between 0 and 100")
    if not (0 < RSI_SELL_THRESHOLD < 100):
        errors.append("RSI_SELL_THRESHOLD must be between 0 and 100")
    if RSI_SELL_THRESHOLD >= RSI_BUY_THRESHOLD:
        errors.append("RSI_SELL_THRESHOLD must be less than RSI_BUY_THRESHOLD")
    
    # Validate ATR ranges
    if ATR_MIN_1M >= ATR_MAX_1M:
        errors.append("ATR_MIN_1M must be less than ATR_MAX_1M")
    if ATR_MIN_5M >= ATR_MAX_5M:
        errors.append("ATR_MIN_5M must be less than ATR_MAX_5M")
    
    # Validate data fetching for SMA calculation
    if CANDLES_1M < SMA_PERIOD + 20:
        errors.append(f"CANDLES_1M ({CANDLES_1M}) should be at least {SMA_PERIOD + 20} for SMA({SMA_PERIOD}) calculation")
    if CANDLES_5M < SMA_PERIOD + 20:
        errors.append(f"CANDLES_5M ({CANDLES_5M}) should be at least {SMA_PERIOD + 20} for SMA({SMA_PERIOD}) calculation")
    
    if errors:
        raise ValueError("Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return True

# Run validation on import
if __name__ == "__main__":
    try:
        validate_config()
        
        # Calculate actual profit/loss values
        calc_profit = TAKE_PROFIT_PERCENT / 100 * FIXED_STAKE * MULTIPLIER
        calc_loss = STOP_LOSS_PERCENT / 100 * FIXED_STAKE * MULTIPLIER
        risk_reward = calc_profit / calc_loss if calc_loss > 0 else 0
        
        print("=" * 60)
        print("✅ CONFIGURATION VALIDATION PASSED!")
        print("=" * 60)
        print("\n📊 TRADING PARAMETERS:")
        print(f"   Symbol: {SYMBOL}")
        print(f"   Market: {MARKET}")
        print(f"   Multiplier: {MULTIPLIER}x")
        
        print("\n💰 RISK MANAGEMENT (SCALPING OPTIMIZED):")
        print(f"   Stake per trade: ${FIXED_STAKE}")
        print(f"   Take Profit: {TAKE_PROFIT_PERCENT}% → ${calc_profit:.2f}")
        print(f"   Stop Loss: {STOP_LOSS_PERCENT}% → ${calc_loss:.2f}")
        print(f"   Risk-to-Reward: 1:{risk_reward:.1f}")
        print(f"   Max Loss Per Trade: ${MAX_LOSS_PER_TRADE}")
        print(f"   Max Daily Loss: ${MAX_DAILY_LOSS}")
        
        print("\n⏰ TRADING LIMITS:")
        print(f"   Cooldown: {COOLDOWN_SECONDS}s ({COOLDOWN_SECONDS//60} minutes)")
        print(f"   Max Trades/Day: {MAX_TRADES_PER_DAY}")
        print(f"   Max Trade Duration: {MAX_TRADE_DURATION}s ({MAX_TRADE_DURATION//60} minutes)")
        
        print("\n📈 STRATEGY PARAMETERS:")
        print(f"   RSI Buy Threshold: >{RSI_BUY_THRESHOLD}")
        print(f"   RSI Sell Threshold: <{RSI_SELL_THRESHOLD}")
        print(f"   ADX Threshold: >{ADX_THRESHOLD}")
        print(f"   Minimum Signal Score: {MINIMUM_SIGNAL_SCORE}")
        print(f"   SMA Period: {SMA_PERIOD}")
        print(f"   EMA Period: {EMA_PERIOD}")
        
        print("\n📊 DATA FETCHING:")
        print(f"   1m Candles: {CANDLES_1M}")
        print(f"   5m Candles: {CANDLES_5M}")
        print(f"   Monitor Interval: {MONITOR_INTERVAL}s")
        
        print("\n🔐 API CONFIGURATION:")
        print(f"   APP_ID: {DERIV_APP_ID}")
        if DERIV_API_TOKEN:
            print(f"   API Token: {'*' * 20}{DERIV_API_TOKEN[-4:]}")
        else:
            print("   ❌ API Token: NOT SET")
        
        print("\n" + "=" * 60)
        print("💡 SCALPING STRATEGY NOTES:")
        print("=" * 60)
        print("• Tight stops (0.2%) with realistic breathing room")
        print("• Quick take profit (0.5%) = $2.00 target")
        print("• Lower stake ($2.5) allows tighter risk management")
        print("• Faster monitoring (3s interval) for quick exits")
        print("• Relaxed RSI thresholds for more trading opportunities")
        print("• 30-minute max trade duration for scalping efficiency")
        print("=" * 60)
        
    except ValueError as e:
        print("=" * 60)
        print("❌ CONFIGURATION ERROR")
        print("=" * 60)
        print(f"\n{e}\n")
        print("=" * 60)