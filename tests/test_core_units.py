import pytest
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

# --- FIXTURES ---

@pytest.fixture
def rm():
    """Initialize RiskManager for testing"""
    from risk_manager import RiskManager
    # Initialize with a base state to prevent TypeError in can_trade
    # last_trade_time is now initialized in __init__ to ancient datetime
    rm = RiskManager()
    return rm

@pytest.fixture
def strategy():
    """Initialize TradingStrategy for testing"""
    from strategy import TradingStrategy
    return TradingStrategy()

@pytest.fixture
def fetcher(mock_env_vars):
    """Initialize DataFetcher with mocked websocket"""
    from data_fetcher import DataFetcher
    with patch("data_fetcher.TokenBucket") as mock_bucket:
        mock_bucket_instance = MagicMock()
        mock_bucket_instance.acquire = AsyncMock()
        mock_bucket.return_value = mock_bucket_instance
        
        f = DataFetcher("fake_token", "1089")
        f.ws = MagicMock()
        f.ws.send = AsyncMock()
        f.ws.recv = AsyncMock()
        f.ws.closed = False  # CRITICAL: prevent ensure_connected from reconnecting
        f.is_connected = True
        return f

# --- RISK MANAGER TESTS ---

def test_risk_manager_init(rm):
    import config
    assert rm.max_trades_per_day == config.MAX_TRADES_PER_DAY
    assert rm.consecutive_losses == 0

def test_can_trade_cooldown(rm):
    # Cooldown logic: if now - last_trade_time < cooldown_seconds: return False
    rm.cooldown_seconds = 300
    now = datetime.now()
    rm.last_trade_time = now - timedelta(seconds=100)
    can_trade, _ = rm.can_trade('R_25')
    assert can_trade is False
    
    rm.last_trade_time = now - timedelta(seconds=600)
    can_trade, _ = rm.can_trade('R_25')
    assert can_trade is True

def test_calculate_risk_amounts(rm):
    signal = {'symbol': 'R_25', 'entry_price': 100.0, 'stop_loss': 99.5, 'take_profit': 102.0}
    # Risk USD = stake * multiplier * entry_dist_pct
    # R_25 multiplier = 160. Stake = 10. dist = 0.5% = 0.005
    # 10 * 160 * 0.005 = 8.0
    amounts = rm.calculate_risk_amounts(signal, 10.0)
    assert amounts['risk_usd'] == pytest.approx(8.0)
    assert amounts['rr_ratio'] == pytest.approx(4.0)

# --- INDICATORS TESTS ---

def test_indicators_basic(sample_ohlc_data):
    from indicators import calculate_atr, calculate_rsi
    df = sample_ohlc_data(n=150)
    from indicators import calculate_all_indicators
    df = calculate_all_indicators(df)
    atr = calculate_atr(df)
    rsi = calculate_rsi(df)
    assert atr.iloc[-1] > 0
    assert 0 <= rsi.iloc[-1] <= 100

def test_detect_movement(sample_ohlc_data):
    from indicators import detect_price_movement
    df = sample_ohlc_data(n=150, trend="bullish")
    pct, pips, _ = detect_price_movement(df)
    assert pct > 0
    assert pips > 0

# --- STRATEGY TESTS ---

def test_strategy_trend_detection(strategy, sample_ohlc_data):
    from indicators import calculate_all_indicators
    # Bullish
    df_bull = sample_ohlc_data(n=200, trend="bullish")
    df_bull.loc[df_bull.index[-10:], 'close'] *= 1.05
    df_bull = calculate_all_indicators(df_bull)
    # The strategy uses 'UP', 'DOWN', 'NEUTRAL'
    assert strategy._determine_trend(df_bull, "1d") == "UP"
    
    # Bearish
    df_bear = sample_ohlc_data(n=200, trend="bearish")
    df_bear.loc[df_bear.index[-10:], 'close'] *= 0.95
    df_bear = calculate_all_indicators(df_bear)
    assert strategy._determine_trend(df_bear, "1d") == "DOWN"

# --- DATA FETCHER TESTS ---

@pytest.mark.asyncio
async def test_fetcher_authorize(fetcher):
    fetcher.ws.recv.return_value = json.dumps({"msg_type": "authorize", "authorize": {"loginid": "CR123"}})
    assert await fetcher.authorize() is True

@pytest.mark.asyncio
async def test_fetcher_candles(fetcher):
    mock_res = {"msg_type": "candles", "candles": [{"epoch": 1700000000, "open": "100", "high": "105", "low": "95", "close": "102"}]}
    fetcher.ws.recv.return_value = json.dumps(mock_res)
    # Fixed granularity passing
    df = await fetcher.fetch_candles("R_25", 60, count=1)
    assert len(df) == 1
    assert df.iloc[0]['close'] == 102.0

# --- REGISTRY TESTS ---

def test_registry_fallback(mock_env_vars):
    from strategy_registry import get_strategy
    strat, _ = get_strategy("Unknown")
    from conservative_strategy import ConservativeStrategy
    assert strat == ConservativeStrategy
