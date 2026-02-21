import pytest
import pandas as pd
from strategy import TradingStrategy

@pytest.fixture
def strategy():
    return TradingStrategy()

def test_strategy_insufficient_data(strategy):
    """Test strategy behavior with empty DataFrames"""
    res = strategy.analyze(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 
                           pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert res['can_trade'] is False
    assert "Insufficient data" in res['details']['reason']

def test_strategy_bullish_alignment(strategy, sample_ohlc_data):
    """Test strategy with all timeframes bullish"""
    n = 200
    data_1w = sample_ohlc_data(n=n, trend="bullish")
    data_1d = sample_ohlc_data(n=n, trend="bullish")
    data_4h = sample_ohlc_data(n=n, trend="bullish")
    data_1h = sample_ohlc_data(n=n, trend="bullish")
    data_5m = sample_ohlc_data(n=n, trend="bullish")
    data_1m = sample_ohlc_data(n=n, trend="bullish")
    
    res = strategy.analyze(data_1m, data_5m, data_1h, data_4h, data_1d, data_1w, symbol="R_25")
    assert "details" in res
    assert "reason" in res["details"]

def test_determine_trend_bullish(strategy, sample_ohlc_data):
    """Test private trend determination logic with significant trend"""
    # Create very strong bullish trend to trigger > 0.2% SMA offset
    df = sample_ohlc_data(n=200, trend="bullish")
    # Manually inflate the last prices to ensure they are > 0.2% above SMA
    df.loc[df.index[-10:], 'close'] *= 1.05 
    from indicators import calculate_all_indicators
    df = calculate_all_indicators(df)
    trend = strategy._determine_trend(df, "1d")
    assert trend == "UP"

def test_determine_trend_bearish(strategy, sample_ohlc_data):
    """Test private trend determination logic with significant trend"""
    df = sample_ohlc_data(n=200, trend="bearish")
    # Manually deflate last prices
    df.loc[df.index[-10:], 'close'] *= 0.95
    from indicators import calculate_all_indicators
    df = calculate_all_indicators(df)
    trend = strategy._determine_trend(df, "1d")
    assert trend == "DOWN"
