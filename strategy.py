"""
Trading Strategy for Deriv R_25 Trading Bot
TOP-DOWN MARKET STRUCTURE: Multi-timeframe level-based trading
Implements Weekly/Daily trend analysis with H4/H1 execution

strategy.py - TOP-DOWN VERSION (FIXED)
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum
import config
from utils import setup_logger, get_signal_emoji

logger = setup_logger()


class TrendBias(Enum):
    """Market trend bias based on structure"""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class LevelType(Enum):
    """Types of price levels"""
    TESTED = "TESTED"           # Historical support/resistance (tested multiple times)
    UNTESTED = "UNTESTED"       # Broken but never retested (primary TP targets)
    MINOR = "MINOR"             # Intraday H4/H1 levels


@dataclass
class PriceLevel:
    """Represents a price level"""
    price: float
    level_type: LevelType
    timeframe: str
    strength: int  # Number of touches (for tested levels)
    broken: bool = False
    retested: bool = False


@dataclass
class MarketStructure:
    """Market structure analysis result"""
    trend_bias: TrendBias
    higher_highs: bool
    higher_lows: bool
    lower_highs: bool
    lower_lows: bool
    structure_shift: bool  # Indicates potential reversal
    last_swing_high: float
    last_swing_low: float


class TradingStrategy:
    """
    Implements Top-Down Market Structure strategy
    
    Trading Rules:
    1. Weekly/Daily analysis determines directional bias
    2. Only trade in direction of higher timeframe trend
    3. Enter on weak retests after momentum breaks
    4. Target untested levels (price magnets)
    5. Never trade in the middle between levels
    """
    
    def __init__(self):
        """Initialize Top-Down strategy"""
        
        # Multi-timeframe settings
        self.structure_timeframes = ['1w', '1d']  # Trend determination
        self.entry_timeframes = ['4h', '1h']      # Execution timeframes
        self.refinement_timeframe = '15m'         # Optional fine-tuning
        
        # Level detection parameters
        self.min_level_touches = 2                # Minimum touches to qualify as "tested"
        self.level_proximity_pct = 0.15           # 0.15% proximity to merge levels
        self.untested_lookback = 100              # Candles to look back for untested levels
        
        # Entry execution parameters
        self.momentum_close_threshold = 1.5       # ATR multiplier for momentum
        self.weak_retest_max_pct = 30             # Max 30% retracement for "weak" retest
        self.middle_zone_pct = 40                 # Avoid middle 40% between levels
        
        # Structure shift detection
        self.require_structure_shift = True       # Must see shift to reverse bias
        self.swing_lookback = 20                  # Candles for swing detection
        
        # Trade execution
        self.multiplier = 160                     # Fixed multiplier value
        
        # Storage
        self.weekly_structure: Optional[MarketStructure] = None
        self.daily_structure: Optional[MarketStructure] = None
        self.current_bias: TrendBias = TrendBias.NEUTRAL
        self.price_levels: List[PriceLevel] = []
        
        logger.info("[OK] Top-Down Strategy initialized")
        logger.info(f"   Multiplier: {self.multiplier}x")
        logger.info(f"   Structure timeframes: {', '.join(self.structure_timeframes)}")
        logger.info(f"   Entry timeframes: {', '.join(self.entry_timeframes)}")
        logger.info(f"   Momentum threshold: {self.momentum_close_threshold}x ATR")
    
    def analyze(self, data_1m: pd.DataFrame, data_5m: pd.DataFrame, 
                data_1h: Optional[pd.DataFrame] = None,
                data_4h: Optional[pd.DataFrame] = None,
                data_1d: Optional[pd.DataFrame] = None,
                data_1w: Optional[pd.DataFrame] = None) -> Dict:
        """
        Main analysis function - Top-Down approach
        
        Args:
            data_1m: 1-minute data (for refinement)
            data_5m: 5-minute data (for execution)
            data_1h: 1-hour data (entry timeframe)
            data_4h: 4-hour data (entry timeframe)
            data_1d: Daily data (structure analysis)
            data_1w: Weekly data (structure analysis)
        
        Returns:
            Trading signal dictionary
        """
        try:
            # Step 1: Validate we have minimum data
            if len(data_1m) < 50 or len(data_5m) < 50:
                return self._create_hold_signal("Insufficient data for analysis")
            
            logger.info("=" * 70)
            logger.info("🔍 TOP-DOWN MARKET ANALYSIS")
            logger.info("=" * 70)
            
            # Step 2: Check for higher timeframe data availability
            if data_1w is None or data_1d is None:
                return self._create_hold_signal("Missing Higher Timeframe Data (Weekly/Daily required)")
            
            if len(data_1w) < self.swing_lookback or len(data_1d) < self.swing_lookback:
                return self._create_hold_signal("Insufficient Weekly/Daily data for structure analysis")
            
            # Step 3: Analyze WEEKLY structure (Master Trend)
            logger.info("📊 Analyzing Weekly Structure (Master Trend)...")
            self.weekly_structure = self._analyze_market_structure(data_1w, timeframe='1w')
            
            logger.info(f"   Weekly Bias: {self.weekly_structure.trend_bias.value}")
            logger.info(f"   Higher Highs: {self.weekly_structure.higher_highs}")
            logger.info(f"   Higher Lows: {self.weekly_structure.higher_lows}")
            logger.info(f"   Lower Highs: {self.weekly_structure.lower_highs}")
            logger.info(f"   Lower Lows: {self.weekly_structure.lower_lows}")
            logger.info(f"   Structure Shift: {self.weekly_structure.structure_shift}")
            
            # Step 4: Analyze DAILY structure (Intermediate Trend)
            logger.info("📊 Analyzing Daily Structure (Intermediate Trend)...")
            self.daily_structure = self._analyze_market_structure(data_1d, timeframe='1d')
            
            logger.info(f"   Daily Bias: {self.daily_structure.trend_bias.value}")
            logger.info(f"   Higher Highs: {self.daily_structure.higher_highs}")
            logger.info(f"   Higher Lows: {self.daily_structure.higher_lows}")
            logger.info(f"   Lower Highs: {self.daily_structure.lower_highs}")
            logger.info(f"   Lower Lows: {self.daily_structure.lower_lows}")
            logger.info(f"   Structure Shift: {self.daily_structure.structure_shift}")
            
            # Step 5: Establish DIRECTIONAL BIAS (alignment required)
            self.current_bias = self._establish_directional_bias(
                self.weekly_structure, 
                self.daily_structure
            )
            
            logger.info("=" * 70)
            logger.info(f"🎯 DIRECTIONAL BIAS ESTABLISHED: {self.current_bias.value}")
            logger.info("=" * 70)
            
            # Log alignment details
            if self.current_bias == TrendBias.BULLISH:
                logger.info("   ✅ Weekly + Daily BOTH BULLISH → Looking for BUY setups only")
            elif self.current_bias == TrendBias.BEARISH:
                logger.info("   ✅ Weekly + Daily BOTH BEARISH → Looking for SELL setups only")
            else:
                logger.info("   ⚠️ Weekly/Daily CONFLICT or NEUTRAL → NO TRADING")
                logger.info(f"      Weekly: {self.weekly_structure.trend_bias.value}")
                logger.info(f"      Daily: {self.daily_structure.trend_bias.value}")
            
            # Step 6: Check directional filter
            if self.current_bias == TrendBias.NEUTRAL:
                return self._create_hold_signal(
                    f"No clear trend bias - Weekly: {self.weekly_structure.trend_bias.value}, "
                    f"Daily: {self.daily_structure.trend_bias.value}"
                )
            
            # Step 7: Detect price levels (on execution timeframes)
            self.price_levels = self._detect_price_levels(data_5m, data_1m)
            
            tested_levels = [l for l in self.price_levels if l.level_type == LevelType.TESTED]
            untested_levels = [l for l in self.price_levels if l.level_type == LevelType.UNTESTED]
            
            logger.info(f"📍 Price Levels Detected:")
            logger.info(f"   Tested levels: {len(tested_levels)}")
            logger.info(f"   Untested levels: {len(untested_levels)} (TP targets)")
            
            # Step 8: Check if price is in no-trade zone (middle between levels)
            current_price = data_1m.iloc[-1]['close']
            in_middle = self._is_in_middle_zone(current_price)
            
            if in_middle:
                return self._create_hold_signal("Price in middle zone (no nearby levels)")
            
            # Step 9: Find nearest levels
            nearest_support, nearest_resistance = self._find_nearest_levels(current_price)
            
            if nearest_support:
                logger.info(f"   Nearest Support: {nearest_support.price:.4f} ({nearest_support.level_type.value})")
            if nearest_resistance:
                logger.info(f"   Nearest Resistance: {nearest_resistance.price:.4f} ({nearest_resistance.level_type.value})")
            
            # Step 10: Check for momentum close
            momentum_break = self._detect_momentum_close(data_1m, data_5m)
            
            if not momentum_break['detected']:
                return self._create_hold_signal(f"No momentum break: {momentum_break['reason']}")
            
            logger.info(f"⚡ Momentum Break Detected:")
            logger.info(f"   Direction: {momentum_break['direction']}")
            logger.info(f"   Strength: {momentum_break['strength']:.2f}x ATR")
            
            # Step 11: Check for weak retest
            retest_status = self._check_weak_retest(data_1m, momentum_break['direction'])
            
            if not retest_status['is_weak_retest']:
                return self._create_hold_signal(f"Retest condition not met: {retest_status['reason']}")
            
            logger.info(f"✅ Weak Retest Confirmed:")
            logger.info(f"   Pullback: {retest_status['pullback_pct']:.1f}%")
            
            # Step 12: Validate trade direction against bias (CRITICAL FILTER)
            signal_direction = momentum_break['direction']
            
            if not self._validate_direction(signal_direction):
                return self._create_hold_signal(
                    f"{signal_direction} signal rejected: Conflicts with {self.current_bias.value} bias "
                    f"(Weekly: {self.weekly_structure.trend_bias.value}, Daily: {self.daily_structure.trend_bias.value})"
                )
            
            logger.info(f"✅ Direction Validated: {signal_direction} aligns with {self.current_bias.value} bias")
            
            # Step 13: Calculate take profit (nearest untested level)
            tp_level = self._find_tp_target(current_price, signal_direction)
            
            if not tp_level:
                return self._create_hold_signal("No untested level target available")
            
            logger.info(f"🎯 Take Profit Target: {tp_level.price:.4f}")
            
            # Step 14: Calculate stop loss (previous swing from DAILY structure)
            sl_level = self._calculate_stop_loss(self.daily_structure, signal_direction)
            
            logger.info(f"🛡️ Stop Loss: {sl_level:.4f}")
            
            # Step 15: Generate final signal
            signal = self._create_signal(
                direction=signal_direction,
                entry_price=current_price,
                tp_price=tp_level.price,
                sl_price=sl_level,
                weekly_structure=self.weekly_structure,
                daily_structure=self.daily_structure,
                momentum=momentum_break,
                retest=retest_status
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"[ERROR] Error in Top-Down analysis: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return self._create_hold_signal(f"Analysis error: {e}")
    
    def _establish_directional_bias(self, weekly: MarketStructure, 
                                    daily: MarketStructure) -> TrendBias:
        """
        Establish directional bias based on Weekly and Daily alignment
        
        Rules:
        - Both BULLISH → BULLISH bias (look for BUY only)
        - Both BEARISH → BEARISH bias (look for SELL only)
        - Conflict or NEUTRAL → NEUTRAL bias (NO TRADING)
        
        This is the "telescope calibration" - we look at the sky (Weekly/Daily)
        to see the storm front before deciding which direction to walk.
        """
        # If either timeframe is NEUTRAL, bias is NEUTRAL
        if weekly.trend_bias == TrendBias.NEUTRAL or daily.trend_bias == TrendBias.NEUTRAL:
            return TrendBias.NEUTRAL
        
        # If both agree on BULLISH
        if weekly.trend_bias == TrendBias.BULLISH and daily.trend_bias == TrendBias.BULLISH:
            return TrendBias.BULLISH
        
        # If both agree on BEARISH
        if weekly.trend_bias == TrendBias.BEARISH and daily.trend_bias == TrendBias.BEARISH:
            return TrendBias.BEARISH
        
        # Conflict between Weekly and Daily (one BULLISH, one BEARISH)
        # This indicates transitional/noisy market → DO NOT TRADE
        return TrendBias.NEUTRAL
    
    def _analyze_market_structure(self, df: pd.DataFrame, timeframe: str) -> MarketStructure:
        """
        Analyze market structure to determine trend bias
        
        Looks for:
        - Higher Highs + Higher Lows = Bullish
        - Lower Highs + Lower Lows = Bearish
        - Mixed = Neutral or Structure Shift
        """
        if len(df) < self.swing_lookback:
            return MarketStructure(
                trend_bias=TrendBias.NEUTRAL,
                higher_highs=False, higher_lows=False,
                lower_highs=False, lower_lows=False,
                structure_shift=False,
                last_swing_high=df['high'].max(),
                last_swing_low=df['low'].min()
            )
        
        # Find swing highs and lows
        swing_highs = self._find_swing_highs(df)
        swing_lows = self._find_swing_lows(df)
        
        # Need at least 2 swings to determine structure
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return MarketStructure(
                trend_bias=TrendBias.NEUTRAL,
                higher_highs=False, higher_lows=False,
                lower_highs=False, lower_lows=False,
                structure_shift=False,
                last_swing_high=df['high'].max(),
                last_swing_low=df['low'].min()
            )
        
        # Check for higher highs
        recent_highs = swing_highs[-2:]
        higher_highs = recent_highs[-1] > recent_highs[-2]
        
        # Check for higher lows
        recent_lows = swing_lows[-2:]
        higher_lows = recent_lows[-1] > recent_lows[-2]
        
        # Check for lower highs
        lower_highs = recent_highs[-1] < recent_highs[-2]
        
        # Check for lower lows
        lower_lows = recent_lows[-1] < recent_lows[-2]
        
        # Determine trend bias
        if higher_highs and higher_lows:
            trend_bias = TrendBias.BULLISH
        elif lower_highs and lower_lows:
            trend_bias = TrendBias.BEARISH
        else:
            trend_bias = TrendBias.NEUTRAL
        
        # Detect structure shift (reversal signals)
        structure_shift = self._detect_structure_shift(swing_highs, swing_lows, trend_bias)
        
        return MarketStructure(
            trend_bias=trend_bias,
            higher_highs=higher_highs,
            higher_lows=higher_lows,
            lower_highs=lower_highs,
            lower_lows=lower_lows,
            structure_shift=structure_shift,
            last_swing_high=swing_highs[-1] if swing_highs else df['high'].max(),
            last_swing_low=swing_lows[-1] if swing_lows else df['low'].min()
        )
    
    def _find_swing_highs(self, df: pd.DataFrame, window: int = 5) -> List[float]:
        """Find swing high points (local maxima)"""
        highs = df['high'].values
        swing_highs = []
        
        for i in range(window, len(highs) - window):
            if all(highs[i] >= highs[i-window:i]) and all(highs[i] >= highs[i+1:i+window+1]):
                swing_highs.append(highs[i])
        
        return swing_highs
    
    def _find_swing_lows(self, df: pd.DataFrame, window: int = 5) -> List[float]:
        """Find swing low points (local minima)"""
        lows = df['low'].values
        swing_lows = []
        
        for i in range(window, len(lows) - window):
            if all(lows[i] <= lows[i-window:i]) and all(lows[i] <= lows[i+1:i+window+1]):
                swing_lows.append(lows[i])
        
        return swing_lows
    
    def _detect_structure_shift(self, swing_highs: List[float], 
                                swing_lows: List[float], 
                                current_bias: TrendBias) -> bool:
        """
        Detect if structure is shifting (potential reversal)
        
        Bullish shift: Failed to make new low, then breaks previous high
        Bearish shift: Failed to make new high, then breaks previous low
        """
        if len(swing_highs) < 3 or len(swing_lows) < 3:
            return False
        
        if current_bias == TrendBias.BULLISH:
            # Look for failure to make new low
            failed_low = swing_lows[-1] > swing_lows[-2]
            # Then break of previous high
            broke_high = swing_highs[-1] < swing_highs[-2]
            return failed_low and broke_high
        
        elif current_bias == TrendBias.BEARISH:
            # Look for failure to make new high
            failed_high = swing_highs[-1] < swing_highs[-2]
            # Then break of previous low
            broke_low = swing_lows[-1] > swing_lows[-2]
            return failed_high and broke_low
        
        return False
    
    def _detect_price_levels(self, df_5m: pd.DataFrame, df_1m: pd.DataFrame) -> List[PriceLevel]:
        """
        Detect all price levels: Tested, Untested, and Minor
        
        - Tested: Historical support/resistance (multiple touches)
        - Untested: Significant highs/lows that were broken but never retested
        - Minor: Recent H1/H4 structure levels
        """
        levels = []
        
        # Use 5m data for level detection
        highs = df_5m['high'].values
        lows = df_5m['low'].values
        
        # Find significant highs and lows
        swing_highs = self._find_swing_highs(df_5m, window=3)
        swing_lows = self._find_swing_lows(df_5m, window=3)
        
        # Cluster nearby levels
        all_levels = swing_highs + swing_lows
        clustered = self._cluster_levels(all_levels)
        
        # Classify each level
        for price in clustered:
            # Count touches
            touches = self._count_level_touches(df_5m, price)
            
            # Check if broken and retested
            broken = self._is_level_broken(df_5m, price)
            retested = self._is_level_retested(df_5m, price) if broken else False
            
            # Classify level type
            if touches >= self.min_level_touches:
                level_type = LevelType.TESTED
            elif broken and not retested:
                level_type = LevelType.UNTESTED  # PRIME TP TARGET
            else:
                level_type = LevelType.MINOR
            
            levels.append(PriceLevel(
                price=price,
                level_type=level_type,
                timeframe='5m',
                strength=touches,
                broken=broken,
                retested=retested
            ))
        
        # Sort by price
        levels.sort(key=lambda x: x.price)
        
        return levels
    
    def _cluster_levels(self, levels: List[float]) -> List[float]:
        """Merge nearby levels within proximity threshold"""
        if not levels:
            return []
        
        sorted_levels = sorted(levels)
        clustered = [sorted_levels[0]]
        
        for level in sorted_levels[1:]:
            last_cluster = clustered[-1]
            proximity_pct = abs(level - last_cluster) / last_cluster * 100
            
            if proximity_pct <= self.level_proximity_pct:
                # Merge into existing cluster (average)
                clustered[-1] = (last_cluster + level) / 2
            else:
                clustered.append(level)
        
        return clustered
    
    def _count_level_touches(self, df: pd.DataFrame, level: float, 
                            tolerance_pct: float = 0.1) -> int:
        """Count how many times price touched a level"""
        touches = 0
        tolerance = level * (tolerance_pct / 100)
        
        for _, row in df.iterrows():
            if abs(row['low'] - level) <= tolerance or abs(row['high'] - level) <= tolerance:
                touches += 1
        
        return touches
    
    def _is_level_broken(self, df: pd.DataFrame, level: float) -> bool:
        """Check if price decisively broke through level"""
        for i in range(len(df) - 1):
            prev_close = df.iloc[i]['close']
            curr_close = df.iloc[i + 1]['close']
            
            # Bullish break (close above after being below)
            if prev_close < level and curr_close > level:
                return True
            
            # Bearish break (close below after being above)
            if prev_close > level and curr_close < level:
                return True
        
        return False
    
    def _is_level_retested(self, df: pd.DataFrame, level: float, 
                          tolerance_pct: float = 0.15) -> bool:
        """Check if level was retested after being broken"""
        tolerance = level * (tolerance_pct / 100)
        broken_idx = None
        
        # Find where level was broken
        for i in range(len(df) - 1):
            prev_close = df.iloc[i]['close']
            curr_close = df.iloc[i + 1]['close']
            
            if (prev_close < level < curr_close) or (prev_close > level > curr_close):
                broken_idx = i + 1
                break
        
        if broken_idx is None:
            return False
        
        # Check if price came back to level after break
        for i in range(broken_idx + 1, len(df)):
            if abs(df.iloc[i]['close'] - level) <= tolerance:
                return True
        
        return False
    
    def _is_in_middle_zone(self, current_price: float) -> bool:
        """Check if price is in the dangerous middle zone between levels"""
        if not self.price_levels:
            return False
        
        # Find nearest support and resistance
        support_levels = [l for l in self.price_levels if l.price < current_price]
        resistance_levels = [l for l in self.price_levels if l.price > current_price]
        
        if not support_levels or not resistance_levels:
            return False
        
        nearest_support = max(support_levels, key=lambda x: x.price)
        nearest_resistance = min(resistance_levels, key=lambda x: x.price)
        
        # Calculate position between levels
        range_size = nearest_resistance.price - nearest_support.price
        distance_from_support = current_price - nearest_support.price
        position_pct = (distance_from_support / range_size) * 100
        
        # Check if in middle zone (avoid 30-70% range)
        lower_bound = (100 - self.middle_zone_pct) / 2
        upper_bound = 100 - lower_bound
        
        in_middle = lower_bound < position_pct < upper_bound
        
        if in_middle:
            logger.debug(f"⚠️ Price at {position_pct:.1f}% between levels (avoid {lower_bound:.0f}-{upper_bound:.0f}%)")
        
        return in_middle
    
    def _find_nearest_levels(self, current_price: float) -> Tuple[Optional[PriceLevel], Optional[PriceLevel]]:
        """Find nearest support and resistance levels"""
        support_levels = [l for l in self.price_levels if l.price < current_price]
        resistance_levels = [l for l in self.price_levels if l.price > current_price]
        
        nearest_support = max(support_levels, key=lambda x: x.price) if support_levels else None
        nearest_resistance = min(resistance_levels, key=lambda x: x.price) if resistance_levels else None
        
        return nearest_support, nearest_resistance
    
    def _detect_momentum_close(self, df_1m: pd.DataFrame, df_5m: pd.DataFrame) -> Dict:
        """
        Detect momentum close: Candle closes decisively beyond a level
        Uses ATR to measure "decisive" movement
        """
        if len(df_1m) < 2:
            return {'detected': False, 'reason': 'Insufficient data'}
        
        current = df_1m.iloc[-1]
        previous = df_1m.iloc[-2]
        atr = df_5m.iloc[-1]['atr'] if 'atr' in df_5m.columns else current.get('atr', 0)
        
        if atr == 0:
            return {'detected': False, 'reason': 'Invalid ATR'}
        
        # Calculate candle movement
        candle_move = abs(current['close'] - current['open'])
        candle_range = current['high'] - current['low']
        
        # Check momentum strength
        momentum_strength = candle_move / atr
        
        if momentum_strength < self.momentum_close_threshold:
            return {
                'detected': False,
                'reason': f'Weak momentum ({momentum_strength:.2f}x < {self.momentum_close_threshold}x ATR)'
            }
        
        # Determine direction
        if current['close'] > current['open']:
            direction = 'BUY'
        else:
            direction = 'SELL'
        
        # Check if close is near high/low (conviction)
        if direction == 'BUY':
            close_near_high = (current['high'] - current['close']) / candle_range < 0.2
            if not close_near_high:
                return {'detected': False, 'reason': 'Close not near high (weak conviction)'}
        else:
            close_near_low = (current['close'] - current['low']) / candle_range < 0.2
            if not close_near_low:
                return {'detected': False, 'reason': 'Close not near low (weak conviction)'}
        
        return {
            'detected': True,
            'direction': direction,
            'strength': momentum_strength,
            'reason': f'Momentum close detected ({momentum_strength:.2f}x ATR)'
        }
    
    def _check_weak_retest(self, df_1m: pd.DataFrame, direction: str) -> Dict:
        """
        Check for weak retest: Price moves back slightly to level after breakout
        Max 30% retracement is considered "weak"
        """
        if len(df_1m) < 5:
            return {'is_weak_retest': False, 'reason': 'Insufficient data'}
        
        recent = df_1m.tail(5)
        
        if direction == 'BUY':
            # Find peak in recent candles
            peak = recent['high'].max()
            current = recent.iloc[-1]['close']
            
            # Calculate pullback
            pullback = ((peak - current) / peak) * 100 if peak > 0 else 0
            
            # Must have some pullback, but not too much
            if pullback < 5:
                return {'is_weak_retest': False, 'reason': 'No pullback detected'}
            
            if pullback > self.weak_retest_max_pct:
                return {
                    'is_weak_retest': False,
                    'reason': f'Pullback too deep ({pullback:.1f}% > {self.weak_retest_max_pct}%)',
                    'pullback_pct': pullback
                }
            
            return {
                'is_weak_retest': True,
                'reason': 'Weak retest confirmed',
                'pullback_pct': pullback
            }
        
        else:  # SELL
            # Find trough in recent candles
            trough = recent['low'].min()
            current = recent.iloc[-1]['close']
            
            # Calculate bounce
            bounce = ((current - trough) / abs(trough)) * 100 if trough != 0 else 0
            
            # Must have some bounce, but not too much
            if bounce < 5:
                return {'is_weak_retest': False, 'reason': 'No bounce detected'}
            
            if bounce > self.weak_retest_max_pct:
                return {
                    'is_weak_retest': False,
                    'reason': f'Bounce too high ({bounce:.1f}% > {self.weak_retest_max_pct}%)',
                    'pullback_pct': bounce
                }
            
            return {
                'is_weak_retest': True,
                'reason': 'Weak retest confirmed',
                'pullback_pct': bounce
            }
    
    def _validate_direction(self, signal_direction: str) -> bool:
        """Validate signal direction against current market bias"""
        if self.current_bias == TrendBias.NEUTRAL:
            return False
        
        if self.current_bias == TrendBias.BULLISH and signal_direction == 'SELL':
            return False
        
        if self.current_bias == TrendBias.BEARISH and signal_direction == 'BUY':
            return False
        
        return True
    
    def _find_tp_target(self, current_price: float, direction: str) -> Optional[PriceLevel]:
        """Find nearest untested level as TP target"""
        untested = [l for l in self.price_levels if l.level_type == LevelType.UNTESTED]
        
        if direction == 'BUY':
            # Find untested resistance above current price
            targets = [l for l in untested if l.price > current_price]
            return min(targets, key=lambda x: x.price) if targets else None
        else:
            # Find untested support below current price
            targets = [l for l in untested if l.price < current_price]
            return max(targets, key=lambda x: x.price) if targets else None
    
    def _calculate_stop_loss(self, structure: MarketStructure, direction: str) -> float:
        """Calculate stop loss based on previous swing"""
        if direction == 'BUY':
            # Place SL below last swing low
            return structure.last_swing_low * 0.998  # 0.2% buffer
        else:
            # Place SL above last swing high
            return structure.last_swing_high * 1.002  # 0.2% buffer
    
    def _create_signal(self, direction: str, entry_price: float, 
                      tp_price: float, sl_price: float,
                      weekly_structure: MarketStructure,
                      daily_structure: MarketStructure,
                      momentum: Dict, 
                      retest: Dict) -> Dict:
        """Create trading signal with all details"""
        
        emoji = get_signal_emoji(direction)
        
        # Calculate risk/reward
        if direction == 'BUY':
            risk = entry_price - sl_price
            reward = tp_price - entry_price
        else:
            risk = sl_price - entry_price
            reward = entry_price - tp_price
        
        rr_ratio = reward / risk if risk > 0 else 0
        
        signal = {
            'signal': direction,
            'strategy': 'TOP_DOWN_STRUCTURE',
            'multiplier': self.multiplier,
            'entry_price': entry_price,
            'take_profit': tp_price,
            'stop_loss': sl_price,
            'risk_reward_ratio': rr_ratio,
            'timestamp': pd.Timestamp.now(),
            'can_trade': True,
            'details': {
                'weekly_bias': weekly_structure.trend_bias.value,
                'daily_bias': daily_structure.trend_bias.value,
                'trend_bias': self.current_bias.value,
                'structure_shift': daily_structure.structure_shift,
                'momentum_strength': momentum['strength'],
                'retest_pullback': retest['pullback_pct'],
                'total_levels': len(self.price_levels),
                'untested_levels': len([l for l in self.price_levels if l.level_type == LevelType.UNTESTED])
            }
        }
        
        logger.info("=" * 70)
        logger.info(f"{emoji} {direction} SIGNAL (TOP-DOWN STRUCTURE)")
        logger.info("=" * 70)
        logger.info(f"   📍 Entry: {entry_price:.4f}")
        logger.info(f"   🎯 Take Profit: {tp_price:.4f}")
        logger.info(f"   🛡️ Stop Loss: {sl_price:.4f}")
        logger.info(f"   📊 Risk/Reward: 1:{rr_ratio:.2f}")
        logger.info(f"   ⚡ Momentum: {momentum['strength']:.2f}x ATR")
        logger.info(f"   🔄 Retest: {retest['pullback_pct']:.1f}% pullback")
        logger.info(f"   📈 Weekly Bias: {weekly_structure.trend_bias.value}")
        logger.info(f"   📈 Daily Bias: {daily_structure.trend_bias.value}")
        logger.info(f"   🎲 Multiplier: {self.multiplier}x")
        logger.info("=" * 70)
        
        return signal
    
    def _create_hold_signal(self, reason: str) -> Dict:
        """Create HOLD signal"""
        return {
            'signal': 'HOLD',
            'strategy': 'TOP_DOWN_STRUCTURE',
            'timestamp': pd.Timestamp.now(),
            'can_trade': False,
            'details': {'reason': reason}
        }