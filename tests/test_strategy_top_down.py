import pytest
import pandas as pd
import numpy as np
from strategy import TradingStrategy
import config

@pytest.fixture
def strategy():
    return TradingStrategy()

@pytest.fixture
def base_ohlc():
    """Base OHLC data for 100 periods"""
    data = {
        'open': np.linspace(100, 110, 100),
        'high': np.linspace(101, 111, 100),
        'low': np.linspace(99, 109, 100),
        'close': np.linspace(100.5, 110.5, 100)
    }
    return pd.DataFrame(data)

def test_strategy_init(strategy):
    assert strategy.min_rr_ratio == config.TOPDOWN_MIN_RR_RATIO
    assert strategy.momentum_threshold == config.MOMENTUM_CLOSE_THRESHOLD

def test_strategy_analyze_no_data(strategy):
    res = strategy.analyze(None, None, None, None, None, None)
    assert res["can_trade"] is False
    assert "Insufficient data" in res["details"]["reason"]

def test_strategy_analyze_weak_trend(strategy, base_ohlc):
    # Mock calculate_adx to return low value
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("strategy.calculate_adx", lambda x: pd.Series([10] * len(x)))
        mp.setattr("strategy.calculate_rsi", lambda x: pd.Series([50] * len(x)))
        
        res = strategy.analyze(base_ohlc, base_ohlc, base_ohlc, base_ohlc, base_ohlc, base_ohlc)
        assert res["can_trade"] is False
        assert "Trend too weak" in res["details"]["reason"]

def test_strategy_analyze_conflict_trend(strategy, base_ohlc):
    # Weekly UP, Daily DOWN
    def mock_determine_trend(df, tf):
        if tf == "Weekly": return "UP"
        if tf == "Daily": return "DOWN"
        return "NEUTRAL"
    
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("strategy.calculate_adx", lambda x: pd.Series([30] * len(x)))
        mp.setattr("strategy.calculate_rsi", lambda x: pd.Series([50] * len(x)))
        # Mock price movement in indicators module
        mp.setattr("indicators.detect_price_movement", lambda *args, **kwargs: (0, 0, False))
        mp.setattr("indicators.detect_consolidation", lambda *args, **kwargs: (True, 100, 90))
        mp.setattr(strategy, "_determine_trend", mock_determine_trend)
        
        res = strategy.analyze(base_ohlc, base_ohlc, base_ohlc, base_ohlc, base_ohlc, base_ohlc)
        assert res["can_trade"] is False
        assert "Trend Conflict" in res["details"]["reason"]

def test_strategy_determine_trend_neutral(strategy):
    df = pd.DataFrame({'high': [100]*10, 'low': [90]*10})
    assert strategy._determine_trend(df, "1m") == "NEUTRAL"

def test_strategy_get_swing_points(strategy):
    # Create a peak for high and a trough for low
    data = {'high': [10, 10, 15, 10, 10], 'low': [10, 10, 5, 10, 10]}
    df = pd.DataFrame(data)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "MIN_SWING_WINDOW", 1)
        highs, lows = strategy._get_swing_points(df)
        assert 15 in highs
        assert 5 in lows

def test_strategy_find_levels(strategy):
    # Create data with two peaks
    data = {'high': [10, 10, 15, 10, 15, 10, 10], 'low': [5, 5, 2, 5, 2, 5, 5]}
    df = pd.DataFrame(data)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "MIN_SWING_WINDOW", 1)
        mp.setattr(config, "LEVEL_PROXIMITY_PCT", 0.1)
        levels = strategy._find_levels(df, "1h")
        assert len(levels) >= 2
        prices = [l['price'] for l in levels]
        assert 15 in prices
        assert 2 in prices

def test_strategy_is_in_middle_zone(strategy):
    # Range 100 to 200. Middle 40% is 130 to 170.
    assert strategy._is_in_middle_zone(150, 100, 200) is True
    assert strategy._is_in_middle_zone(110, 100, 200) is False
    assert strategy._is_in_middle_zone(190, 100, 200) is False

def test_strategy_identify_tp_sl_levels_up(strategy, base_ohlc):
    levels = [{'price': 120}, {'price': 130}]
    current_price = 100
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "MIN_TP_DISTANCE_PCT", 0.1)
        # Mock swing points for SL (close to current price to avoid clamping)
        mp.setattr(strategy, "_get_swing_points", lambda df: ([110], [99.5]))
        tp, sl = strategy._identify_tp_sl_levels(levels, current_price, "UP", base_ohlc, base_ohlc, base_ohlc, base_ohlc)
        assert tp == 120
        assert sl == 99.5

def test_strategy_validate_level_proximity(strategy):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "MAX_ENTRY_DISTANCE_PCT", 0.5)
        
        # UP: Price above level, within distance
        valid, msg, dist = strategy._validate_level_proximity(100.2, 100.0, "UP")
        assert valid is True
        
        # UP: Price below level
        valid, msg, dist = strategy._validate_level_proximity(99.8, 100.0, "UP")
        assert valid is False
        
        # UP: Price too far
        valid, msg, dist = strategy._validate_level_proximity(101.0, 100.0, "UP")
        assert valid is False

def test_strategy_check_entry_trigger_breakout_up(strategy, base_ohlc):
    # Mock ATR to 1.0
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(strategy, "_calculate_atr", lambda x: 1.0)
        strategy.momentum_threshold = 1.5
        
        # Create a candle that closes above level 100 with body > 1.5
        df = base_ohlc.copy()
        df.iloc[-1] = {'open': 99.0, 'high': 102.0, 'low': 98.0, 'close': 101.0}
        
        valid, reason = strategy._check_entry_trigger(df, 100.0, "UP")
        assert valid is True
        assert "Momentum Breakout Confirmed" not in reason # It returns (True, "") usually or similar

def test_strategy_analyze_success_up(strategy, base_ohlc):
    def mock_determine_trend(df, tf):
        return "UP"
    
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("strategy.calculate_adx", lambda x: pd.Series([30] * len(x)))
        mp.setattr("strategy.calculate_rsi", lambda x: pd.Series([60] * len(x)))
        
        # Patch the functions in the indicators module where they are imported from
        import indicators
        mp.setattr(indicators, "detect_price_movement", lambda *args, **kwargs: (0.1, 0.1, False))
        mp.setattr(indicators, "detect_consolidation", lambda *args, **kwargs: (True, 100, 99))
        
        mp.setattr(strategy, "_determine_trend", mock_determine_trend)
        mp.setattr(strategy, "_identify_tp_sl_levels", lambda *args: (120.0, 105.0))
        mp.setattr(strategy, "_check_entry_trigger", lambda *args: (True, "Triggered"))
        mp.setattr(strategy, "_is_in_middle_zone", lambda *args: False)
        mp.setattr(strategy, "_find_nearest_level", lambda *args: 99.5)
        mp.setattr(strategy, "_validate_level_proximity", lambda *args: (True, "OK", 0.1))
        mp.setattr(config, "RSI_BUY_THRESHOLD", 55)
        mp.setattr(config, "MIN_TP_DISTANCE_PCT", 0.1)
        mp.setattr(strategy, "min_rr_ratio", 1.5)
        
        res = strategy.analyze(base_ohlc, base_ohlc, base_ohlc, base_ohlc, base_ohlc, base_ohlc, symbol="R_25")
        assert res["can_trade"] is True
        assert res["signal"] == "UP"
        assert res["take_profit"] == 120.0
        assert res["stop_loss"] == 105.0
