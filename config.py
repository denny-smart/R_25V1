"""
Configuration Settings for Deriv R_25 Multipliers Trading Bot
ENHANCED VERSION - With Multi-Timeframe Top-Down Strategy
✅ Top-Down market structure analysis
✅ Dynamic TP/SL based on levels
✅ Two-phase cancellation risk management
config.py - PRODUCTION READY WITH TOP-DOWN STRATEGY
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==================== API CREDENTIALS ====================
API_TOKEN = os.getenv("API_TOKEN")
APP_ID = os.getenv("APP_ID", "1089")

DERIV_API_TOKEN = API_TOKEN if API_TOKEN else os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = APP_ID if APP_ID and APP_ID != "1089" else os.getenv("DERIV_APP_ID", "1089")

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
CONTRACT_TYPE = "MULTUP"           # Multiplier Up
CONTRACT_TYPE_DOWN = "MULTDOWN"    # Multiplier Down

# ==================== RISK MANAGEMENT ====================
FIXED_STAKE = 10.0                 # $10 stake
MULTIPLIER = 160                   # 160x multiplier (changed from 400x for safety)

# ⭐ TWO-PHASE CANCELLATION PARAMETERS ⭐
ENABLE_CANCELLATION = True         # Enable 5-minute cancellation feature
CANCELLATION_DURATION = 300        # 5 minutes (300 seconds)
CANCELLATION_FEE = 0.45            # Actual Deriv cancellation cost: $0.45
CANCELLATION_THRESHOLD = 0.70      # Cancel if 70% of cancellation cost reached
CANCELLATION_CHECK_INTERVAL = 5    # Check every 5 seconds during cancellation

# ⭐ TWO-PHASE RISK MANAGEMENT ⭐
# Phase 1: During Cancellation (First 5 minutes)
# - Risk: Limited to cancellation fee (typically small % of stake)
# - Action: Cancel if price moves 70% toward cancellation threshold

# Phase 2: After Cancellation Expires (Full Commitment)
POST_CANCEL_STOP_LOSS_PERCENT = 0.0125   # 5% of stake loss = 0.0125% price move with 400x
POST_CANCEL_TAKE_PROFIT_PERCENT = 0.0375  # 15% price move target = 0.0375% with 400x

# Legacy parameters (for backward compatibility if cancellation disabled)
TAKE_PROFIT_PERCENT = 0.05         # 0.05% TP (used if cancellation disabled)
STOP_LOSS_PERCENT = 0.025          # 0.025% SL (used if cancellation disabled)

MAX_LOSS_PER_TRADE = 1.0           # Maximum loss per trade (USD)
COOLDOWN_SECONDS = 180             # 3 minutes between trades
MAX_TRADES_PER_DAY = 30            # Maximum trades per day
MAX_DAILY_LOSS = 10.0              # Stop if lose $10 in a day

# Valid multipliers for R_25
VALID_MULTIPLIERS = [160, 400, 800, 1200, 1600]

# ==================== DATA FETCHING ====================
CANDLES_1M = 150                   # 1-minute candles
CANDLES_5M = 120                   # 5-minute candles
MAX_RETRIES = 3
RETRY_DELAY = 2

# ==================== STRATEGY PARAMETERS ====================
# ATR Validation Ranges
ATR_MIN_1M = 0.05                 # Minimum 1m ATR
ATR_MAX_1M = 2.0                  # Maximum 1m ATR
ATR_MIN_5M = 0.10                 # Minimum 5m ATR
ATR_MAX_5M = 3.5                  # Maximum 5m ATR

# RSI Thresholds
RSI_BUY_THRESHOLD = 58            # Buy signal threshold
RSI_SELL_THRESHOLD = 42           # Sell signal threshold

# ADX Threshold
ADX_THRESHOLD = 22                # Minimum trend strength

# Moving Averages
SMA_PERIOD = 100
EMA_PERIOD = 20

# Signal Scoring
MINIMUM_SIGNAL_SCORE = 6          # Minimum score to trade

# Filters
VOLATILITY_SPIKE_MULTIPLIER = 2.0
WEAK_CANDLE_MULTIPLIER = 0.35

# ==================== TRADE MONITORING ====================
MAX_TRADE_DURATION = 900           # 15 minutes max after cancellation
MONITOR_INTERVAL = 2               # Check every 2 seconds

# ==================== LOGGING ====================
LOG_FILE = "trading_bot.log"
LOG_LEVEL = "INFO"

# ==================== WEBSOCKET ====================
WS_URL = "wss://ws.derivws.com/websockets/v3"
WS_TIMEOUT = 30


# ============================================================================
# TOP-DOWN MULTI-TIMEFRAME STRATEGY SETTINGS
# ============================================================================

# ==================== STRATEGY SELECTION ====================
USE_TOPDOWN_STRATEGY = True        # True = Top-Down, False = Legacy Scalping

# ==================== MULTI-TIMEFRAME DATA FETCHING ====================
FETCH_WEEKLY = True                # Fetch weekly data for major trend structure
FETCH_DAILY = True                 # Fetch daily data for intermediate structure
FETCH_4H = True                    # Fetch 4H data for refined entry zones
FETCH_1H = True                    # Fetch 1H data for precise entries

# Candle Counts per Timeframe (used by fetch_all_timeframes)
CANDLES_1W = 52                    # 1 year of weekly candles
CANDLES_1D = 100                   # ~3 months of daily candles
CANDLES_4H = 200                   # ~33 days of 4H candles
CANDLES_1H = 200                   # ~8 days of hourly candles
# CANDLES_5M and CANDLES_1M already defined above

# ==================== LEVEL DETECTION SETTINGS ====================
MIN_LEVEL_TOUCHES = 2              # Minimum touches to qualify as "tested level"
LEVEL_PROXIMITY_PCT = 0.15         # Merge levels within 0.15% of each other
UNTESTED_LOOKBACK = 100            # Candles to look back for untested levels
MAX_LEVELS_PER_TIMEFRAME = 5       # Track top 5 most significant levels

# ==================== ENTRY EXECUTION CRITERIA ====================
MOMENTUM_CLOSE_THRESHOLD = 1.5     # ATR multiplier for momentum close (1.5x = strong)
WEAK_RETEST_MAX_PCT = 30           # Max 30% retracement qualifies as "weak" retest
MIDDLE_ZONE_PCT = 40               # Avoid middle 40% between levels (dangerous zone)
REQUIRE_LEVEL_PROXIMITY = True     # Must be within 0.2% of a key level to enter

# ==================== MARKET STRUCTURE ANALYSIS ====================
SWING_LOOKBACK = 20                # Candles for swing high/low detection
REQUIRE_STRUCTURE_SHIFT = True     # Must see structure shift to reverse bias
MIN_SWING_WINDOW = 5               # Minimum window size for swing point detection
STRUCTURE_CONFIRMATION_CANDLES = 3 # Wait N candles to confirm structure break

# ==================== RISK MANAGEMENT FOR TOP-DOWN ====================
TOPDOWN_USE_DYNAMIC_TP = True      # TP based on untested levels (not fixed %)
TOPDOWN_USE_STRUCTURE_SL = True    # SL based on swing points (not fixed %)
TOPDOWN_MIN_RR_RATIO = 2.0         # Minimum 1:2.0 risk/reward to take trade
TOPDOWN_MAX_SL_DISTANCE_PCT = 0.5  # Maximum SL distance: 0.5% from entry

# ==================== TP/SL BUFFER SETTINGS ====================
TP_BUFFER_PCT = 0.1                # 0.1% before actual level (early exit buffer)
SL_BUFFER_PCT = 0.2                # 0.2% beyond swing (safety margin)
MIN_TP_DISTANCE_PCT = 0.2          # Minimum TP distance from entry

# ==================== CONFLUENCE SCORING ====================
CONFLUENCE_WEIGHT_HIGHER_TF = 2.0  # Higher timeframe levels weighted 2x
CONFLUENCE_WEIGHT_UNTESTED = 1.5   # Untested levels weighted 1.5x
MIN_CONFLUENCE_SCORE = 3.0         # Minimum score to consider level valid


# ==================== VALIDATION ====================
def validate_config():
    """Validate configuration settings"""
    errors = []
    
    if not DERIV_API_TOKEN:
        errors.append("API_TOKEN is not set in .env file")
    
    # Validate contract types
    if CONTRACT_TYPE not in ["MULTUP", "MULTDOWN"]:
        errors.append(f"CONTRACT_TYPE must be MULTUP or MULTDOWN, not {CONTRACT_TYPE}")
    
    # Validate risk parameters
    if FIXED_STAKE <= 0:
        errors.append("FIXED_STAKE must be positive")
    if MULTIPLIER not in VALID_MULTIPLIERS:
        errors.append(f"MULTIPLIER must be one of {VALID_MULTIPLIERS}")
    
    # Validate cancellation parameters
    if ENABLE_CANCELLATION and not USE_TOPDOWN_STRATEGY:
        if CANCELLATION_DURATION < 60 or CANCELLATION_DURATION > 600:
            errors.append("CANCELLATION_DURATION should be between 60-600 seconds")
        if CANCELLATION_FEE <= 0:
            errors.append("CANCELLATION_FEE must be positive")
        if not (0.5 <= CANCELLATION_THRESHOLD <= 0.9):
            errors.append("CANCELLATION_THRESHOLD should be between 0.5 and 0.9")
        if POST_CANCEL_STOP_LOSS_PERCENT <= 0:
            errors.append("POST_CANCEL_STOP_LOSS_PERCENT must be positive")
        if POST_CANCEL_TAKE_PROFIT_PERCENT <= 0:
            errors.append("POST_CANCEL_TAKE_PROFIT_PERCENT must be positive")
    
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
    
    if errors:
        raise ValueError("Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return True


def validate_topdown_config():
    """Validate Top-Down strategy configuration"""
    errors = []
    
    if USE_TOPDOWN_STRATEGY:
        # Validate momentum threshold
        if MOMENTUM_CLOSE_THRESHOLD < 1.0 or MOMENTUM_CLOSE_THRESHOLD > 3.0:
            errors.append("MOMENTUM_CLOSE_THRESHOLD should be between 1.0 and 3.0")
        
        # Validate retest percentage
        if WEAK_RETEST_MAX_PCT < 10 or WEAK_RETEST_MAX_PCT > 50:
            errors.append("WEAK_RETEST_MAX_PCT should be between 10 and 50")
        
        # Validate middle zone
        if MIDDLE_ZONE_PCT < 20 or MIDDLE_ZONE_PCT > 60:
            errors.append("MIDDLE_ZONE_PCT should be between 20 and 60")
        
        # Validate level proximity
        if LEVEL_PROXIMITY_PCT <= 0 or LEVEL_PROXIMITY_PCT > 1.0:
            errors.append("LEVEL_PROXIMITY_PCT should be between 0.01 and 1.0")
        
        # Validate risk/reward
        if TOPDOWN_MIN_RR_RATIO < 1.0:
            errors.append("TOPDOWN_MIN_RR_RATIO must be at least 1.0")
        
        # Validate SL distance
        if TOPDOWN_MAX_SL_DISTANCE_PCT <= 0 or TOPDOWN_MAX_SL_DISTANCE_PCT > 2.0:
            errors.append("TOPDOWN_MAX_SL_DISTANCE_PCT should be between 0.01 and 2.0")
        
        # Validate swing settings
        if SWING_LOOKBACK < 5 or SWING_LOOKBACK > 50:
            errors.append("SWING_LOOKBACK should be between 5 and 50")
        
        if MIN_SWING_WINDOW < 2 or MIN_SWING_WINDOW > SWING_LOOKBACK:
            errors.append(f"MIN_SWING_WINDOW should be between 2 and {SWING_LOOKBACK}")
    
    if errors:
        raise ValueError("Top-Down configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return True


if __name__ == "__main__":
    try:
        validate_config()
        
        print("=" * 75)
        print("✅ MULTI-STRATEGY CONFIGURATION VALIDATED")
        print("=" * 75)
        
        print("\n📊 TRADING PARAMETERS:")
        print(f"   Symbol: {SYMBOL}")
        print(f"   Multiplier: {MULTIPLIER}x")
        print(f"   Stake: ${FIXED_STAKE}")
        
        # Display strategy-specific configuration
        if USE_TOPDOWN_STRATEGY:
            validate_topdown_config()
            
            print("\n" + "=" * 75)
            print("🎯 TOP-DOWN MULTI-TIMEFRAME STRATEGY")
            print("=" * 75)
            
            print("\n📈 TIMEFRAMES ANALYZED:")
            print(f"   Weekly (1w): {CANDLES_1W} candles {'✓' if FETCH_WEEKLY else '✗'}")
            print(f"   Daily (1d): {CANDLES_1D} candles {'✓' if FETCH_DAILY else '✗'}")
            print(f"   4-Hour (4h): {CANDLES_4H} candles {'✓' if FETCH_4H else '✗'}")
            print(f"   1-Hour (1h): {CANDLES_1H} candles {'✓' if FETCH_1H else '✗'}")
            print(f"   5-Minute (5m): {CANDLES_5M} candles ✓")
            print(f"   1-Minute (1m): {CANDLES_1M} candles ✓")
            
            print("\n🎯 ENTRY CRITERIA:")
            print(f"   Momentum Threshold: {MOMENTUM_CLOSE_THRESHOLD}x ATR")
            print(f"   Weak Retest Max: {WEAK_RETEST_MAX_PCT}%")
            print(f"   Middle Zone Avoid: {MIDDLE_ZONE_PCT}%")
            print(f"   Level Proximity Required: {'Yes' if REQUIRE_LEVEL_PROXIMITY else 'No'}")
            
            print("\n📊 STRUCTURE ANALYSIS:")
            print(f"   Swing Lookback: {SWING_LOOKBACK} candles")
            print(f"   Structure Shift Required: {'Yes' if REQUIRE_STRUCTURE_SHIFT else 'No'}")
            print(f"   Min Swing Window: {MIN_SWING_WINDOW} candles")
            print(f"   Min Level Touches: {MIN_LEVEL_TOUCHES}")
            
            print("\n💰 RISK MANAGEMENT:")
            print(f"   Min R:R Ratio: 1:{TOPDOWN_MIN_RR_RATIO}")
            print(f"   Dynamic TP: {'Enabled' if TOPDOWN_USE_DYNAMIC_TP else 'Disabled'}")
            print(f"   Dynamic SL: {'Enabled' if TOPDOWN_USE_STRUCTURE_SL else 'Disabled'}")
            print(f"   Max SL Distance: {TOPDOWN_MAX_SL_DISTANCE_PCT}%")
            print(f"   TP Buffer: {TP_BUFFER_PCT}%")
            print(f"   SL Buffer: {SL_BUFFER_PCT}%")
            
            print("\n🔍 LEVEL DETECTION:")
            print(f"   Level Proximity: {LEVEL_PROXIMITY_PCT}%")
            print(f"   Untested Lookback: {UNTESTED_LOOKBACK} candles")
            print(f"   Max Levels/TF: {MAX_LEVELS_PER_TIMEFRAME}")
            print(f"   Min Confluence Score: {MIN_CONFLUENCE_SCORE}")
            
        else:
            print("\n" + "=" * 75)
            print("⚡ LEGACY SCALPING STRATEGY")
            print("=" * 75)
            
            if ENABLE_CANCELLATION:
                print("\n🛡️ PHASE 1: CANCELLATION PHASE (First 5 minutes)")
                print(f"   Duration: {CANCELLATION_DURATION}s ({CANCELLATION_DURATION//60} min)")
                print(f"   Cancellation Fee: ${CANCELLATION_FEE:.2f}")
                print(f"   Auto-Cancel Threshold: {CANCELLATION_THRESHOLD*100:.0f}%")
                print(f"   Check Interval: {CANCELLATION_CHECK_INTERVAL}s")
                
                post_sl_amount = POST_CANCEL_STOP_LOSS_PERCENT / 100 * FIXED_STAKE * MULTIPLIER
                post_tp_amount = POST_CANCEL_TAKE_PROFIT_PERCENT / 100 * FIXED_STAKE * MULTIPLIER
                
                print("\n🎯 PHASE 2: COMMITTED PHASE (After 5 minutes)")
                print(f"   Stop Loss: {POST_CANCEL_STOP_LOSS_PERCENT}% → ${post_sl_amount:.2f}")
                print(f"   Take Profit: {POST_CANCEL_TAKE_PROFIT_PERCENT}% → ${post_tp_amount:.2f}")
                print(f"   Risk-to-Reward: 1:{post_tp_amount/post_sl_amount:.1f}")
            else:
                legacy_tp = TAKE_PROFIT_PERCENT / 100 * FIXED_STAKE * MULTIPLIER
                legacy_sl = STOP_LOSS_PERCENT / 100 * FIXED_STAKE * MULTIPLIER
                print("\n⚠️ CANCELLATION DISABLED - Using legacy TP/SL")
                print(f"   Take Profit: ${legacy_tp:.2f}")
                print(f"   Stop Loss: ${legacy_sl:.2f}")
        
        print("\n⏰ TRADING LIMITS:")
        print(f"   Cooldown: {COOLDOWN_SECONDS}s ({COOLDOWN_SECONDS//60} min)")
        print(f"   Max Trades/Day: {MAX_TRADES_PER_DAY}")
        print(f"   Max Daily Loss: ${MAX_DAILY_LOSS}")
        
        print("\n🔐 API CONFIGURATION:")
        print(f"   APP_ID: {DERIV_APP_ID}")
        if DERIV_API_TOKEN:
            print(f"   API Token: {'*' * 20}{DERIV_API_TOKEN[-4:]}")
        
        print("\n" + "=" * 75)
        print("🚀 CONFIGURATION READY")
        print("=" * 75)
        
    except ValueError as e:
        print("=" * 75)
        print("❌ CONFIGURATION ERROR")
        print("=" * 75)
        print(f"\n{e}\n")
        print("=" * 75)