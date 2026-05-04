import pandas as pd
import pytest
from unittest.mock import patch

from risefallbot.rf_strategy import RiseFallStrategy


@pytest.fixture
def strategy():
    with patch("risefallbot.rf_strategy.rf_config") as mock_config:
        mock_config.RF_SYMBOLS = ["R_25"]
        mock_config.RF_SR_CANDLE_COUNT = 10
        mock_config.RF_SR_PIVOT_WINDOW = 2
        mock_config.RF_SR_MIN_TOUCHES = 1
        yield RiseFallStrategy()


def test_metadata(strategy):
    assert strategy.get_strategy_name() == "RiseFall"
    assert strategy.get_required_timeframes() == ["1m"]


def test_analyze_insufficient_candle_history(strategy):
    # Pass fewer than RF_SR_CANDLE_COUNT candles
    df = pd.DataFrame({
        "open": [100.0] * 5,
        "high": [101.0] * 5,
        "low": [99.0] * 5,
        "close": [100.0] * 5,
        "timestamp": [1600000000 + i * 60 for i in range(5)]
    })
    assert strategy.analyze(data_1m=df, symbol="R_25") is None
    meta = strategy.get_last_analysis("R_25")
    assert meta["code"] == "insufficient_candle_history"


def test_analyze_empty_data(strategy):
    assert strategy.analyze(data_1m=None, symbol="R_25") is None
    assert strategy.analyze(data_1m=pd.DataFrame(), symbol="R_25") is None


def test_symbol_not_allowed_rejected(strategy):
    df = pd.DataFrame({
        "open": [100.0] * 12,
        "high": [101.0] * 12,
        "low": [99.0] * 12,
        "close": [100.0] * 12,
        "timestamp": [1600000000 + i * 60 for i in range(12)]
    })
    assert strategy.analyze(data_1m=df, symbol="R_100") is None
    meta = strategy.get_last_analysis("R_100")
    assert meta["code"] == "symbol_not_allowed"


def test_no_zones_detected(strategy):
    # A straight upward line will have no valid pivot highs/lows inside the window
    df = pd.DataFrame({
        "open": [100.0 + i for i in range(15)],
        "high": [100.0 + i for i in range(15)],
        "low": [100.0 + i for i in range(15)],
        "close": [100.0 + i for i in range(15)],
        "timestamp": [1600000000 + i * 60 for i in range(15)]
    })
    assert strategy.analyze(data_1m=df, symbol="R_25") is None
    meta = strategy.get_last_analysis("R_25")
    assert meta["code"] == "no_zones_detected"


def test_normalize_candles(strategy):
    raw = [{"open": 1, "high": 2, "low": 0, "close": 1, "epoch": 1600000000}]
    df = strategy._normalize_candles(raw)
    assert not df.empty
    assert "timestamp" in df.columns
    assert "datetime" in df.columns
    assert df["open"].iloc[0] == 1.0


def test_patterns(strategy):
    # _is_bullish_engulf
    prev = pd.Series({"open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0})
    curr = pd.Series({"open": 98.5, "high": 102.0, "low": 98.0, "close": 101.5})
    assert strategy._is_bullish_engulf(prev, curr) is True
    
    # _is_bearish_engulf
    prev = pd.Series({"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0})
    curr = pd.Series({"open": 100.5, "high": 101.5, "low": 96.0, "close": 98.5})
    assert strategy._is_bearish_engulf(prev, curr) is True

    # _is_bullish_pin_bar: long lower wick, close near top
    zone = {"type": "support", "level": 100.0, "upper": 100.1, "lower": 99.9}
    candle = pd.Series({"open": 101.0, "high": 101.5, "low": 95.0, "close": 101.2})
    assert strategy._is_bullish_pin_bar(candle, zone) is True

    # _is_bearish_pin_bar: long upper wick, close near bottom
    zone = {"type": "resistance", "level": 100.0, "upper": 100.1, "lower": 99.9}
    candle = pd.Series({"open": 96.0, "high": 102.0, "low": 95.5, "close": 95.8})
    assert strategy._is_bearish_pin_bar(candle, zone) is True


def test_analyze_success_support_call(strategy):
    data = []
    for i in range(8):
        data.append({"open": 105.0, "high": 105.0, "low": 105.0, "close": 105.0, "epoch": 1600000000 + i*60})
    
    data.append({"open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0, "epoch": 1600000000 + 8*60})
    data.append({"open": 101.0, "high": 101.0, "low": 101.0, "close": 101.0, "epoch": 1600000000 + 9*60})
    data.append({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "epoch": 1600000000 + 10*60}) # Low
    data.append({"open": 101.0, "high": 101.0, "low": 101.0, "close": 101.0, "epoch": 1600000000 + 11*60})
    data.append({"open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0, "epoch": 1600000000 + 12*60})
    
    data.append({"open": 102.0, "high": 102.5, "low": 101.5, "close": 101.5, "epoch": 1600000000 + 13*60})
    data.append({"open": 101.0, "high": 103.0, "low": 99.9, "close": 102.5, "epoch": 1600000000 + 14*60})

    df = pd.DataFrame(data)
    strategy.sr_candle_count = 15
    result = strategy.analyze(data_1m=df, symbol="R_25")
    
    assert result is not None
    assert result["direction"] == "CALL"
    assert result["zone_type"] == "support"
    assert result["confirmation_pattern"] == "bullish_engulf"


def test_analyze_success_resistance_put(strategy):
    data = []
    for i in range(8):
        data.append({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "epoch": 1600000000 + i*60})
        
    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 8*60})
    data.append({"open": 109.0, "high": 109.0, "low": 109.0, "close": 109.0, "epoch": 1600000000 + 9*60})
    data.append({"open": 110.0, "high": 110.0, "low": 110.0, "close": 110.0, "epoch": 1600000000 + 10*60}) # High
    data.append({"open": 109.0, "high": 109.0, "low": 109.0, "close": 109.0, "epoch": 1600000000 + 11*60})
    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 12*60})
    
    data.append({"open": 105.0, "high": 107.0, "low": 105.0, "close": 107.0, "epoch": 1600000000 + 13*60})
    data.append({"open": 107.5, "high": 110.1, "low": 104.0, "close": 104.5, "epoch": 1600000000 + 14*60})
    
    df = pd.DataFrame(data)
    strategy.sr_candle_count = 15
    result = strategy.analyze(data_1m=df, symbol="R_25")
    
    assert result is not None
    assert result["direction"] == "PUT"
    assert result["zone_type"] == "resistance"
    assert result["confirmation_pattern"] == "bearish_engulf"


def test_analyze_no_confirmation(strategy):
    data = []
    for i in range(8):
        data.append({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "epoch": 1600000000 + i*60})
        
    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 8*60})
    data.append({"open": 109.0, "high": 109.0, "low": 109.0, "close": 109.0, "epoch": 1600000000 + 9*60})
    data.append({"open": 110.0, "high": 110.0, "low": 110.0, "close": 110.0, "epoch": 1600000000 + 10*60}) # High
    data.append({"open": 109.0, "high": 109.0, "low": 109.0, "close": 109.0, "epoch": 1600000000 + 11*60})
    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 12*60})
    
    data.append({"open": 105.0, "high": 105.0, "low": 105.0, "close": 105.0, "epoch": 1600000000 + 13*60})
    data.append({"open": 105.0, "high": 110.1, "low": 104.0, "close": 110.0, "epoch": 1600000000 + 14*60})
    
    df = pd.DataFrame(data)
    strategy.sr_candle_count = 15
    result = strategy.analyze(data_1m=df, symbol="R_25")
    
    assert result is None
    meta = strategy.get_last_analysis("R_25")
    assert meta["code"] == "no_zone_touch"
