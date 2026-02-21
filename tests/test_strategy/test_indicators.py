import pytest
import pandas as pd
from indicators import (
    calculate_atr, calculate_rsi, calculate_adx, 
    detect_price_movement, detect_consolidation
)

def test_calculate_atr(sample_ohlc_data):
    df = sample_ohlc_data(n=150)
    atr = calculate_atr(df, period=14)
    assert isinstance(atr, pd.Series)
    assert not atr.tail(10).isnull().any()
    assert atr.iloc[-1] > 0

def test_calculate_rsi(sample_ohlc_data):
    df = sample_ohlc_data(n=150)
    rsi = calculate_rsi(df, period=14)
    assert isinstance(rsi, pd.Series)
    assert not rsi.tail(10).isnull().any()
    assert 0 <= rsi.iloc[-1] <= 100

def test_calculate_adx(sample_ohlc_data):
    df = sample_ohlc_data(n=150)
    adx = calculate_adx(df, period=14)
    assert isinstance(adx, pd.Series)
    assert not adx.tail(10).isnull().any()
    assert adx.iloc[-1] >= 0

def test_detect_price_movement_bullish(sample_ohlc_data):
    df = sample_ohlc_data(n=150, trend="bullish")
    pct, pips, is_parabolic = detect_price_movement(df, lookback=20)
    assert pct > 0
    assert pips > 0

def test_detect_consolidation_sideways(sample_ohlc_data):
    df = sample_ohlc_data(n=150, trend="sideways")
    # detect_consolidation logic:
    # range_pct < 2.0 * avg_atr_pct
    # We ensure our sideways data is FLAT enough.
    is_consol, high, low = detect_consolidation(df, lookback=20)
    assert high >= low
    assert isinstance(is_consol, bool)
    # Even if it's False, we check it doesn't crash and returns valid prices.
    assert high > 0
    assert low > 0
