import pytest
import pandas as pd
import numpy as np
from conservative_strategy.strategy import TradingStrategy

@pytest.fixture
def strategy():
    return TradingStrategy()

def _make_df(n=20, close_vals=None, high_vals=None, low_vals=None):
    df = pd.DataFrame({
        'open': [100.0] * n,
        'high': high_vals if high_vals else [101.0] * n,
        'low': low_vals if low_vals else [99.0] * n,
        'close': close_vals if close_vals else [100.0] * n,
    })
    return df

def test_analyze_fake_breakout_data_validation(strategy):
    res = strategy._analyze_fake_breakout(None, None, None, "R_25")
    assert res["can_trade"] is False
    assert "Insufficient data" in res["details"]["reason"]

def test_analyze_fake_breakout_no_setup(strategy):
    # Setup data where price stays inside range
    d15m = _make_df(150)
    d1d = _make_df(100)
    d1w = _make_df(52)
    
    # Mock find_levels to return a resistance far away
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(strategy, "_find_levels", lambda *_a, **_k: [{'price': 150.0, 'type': 'resistance'}])
        mp.setattr(strategy, "_determine_trend", lambda *_a, **_k: "UP")
        
        res = strategy._analyze_fake_breakout(d15m, d1d, d1w, "R_25")
        assert res["can_trade"] is False
        assert "No Fake Breakout Reversal" in res["details"]["reason"]

def test_analyze_fake_breakout_success_sell(strategy):
    # Resistance at 110.0
    # Price breaks above 110.0 and then reverses below it.
    
    # M15 Data
    close = [100.0] * 140 + [110.5, 111.0, 110.5, 109.0] # Reversed below 110
    high = [101.0] * 140 + [111.0, 112.0, 111.0, 110.0]
    low = [99.0] * 140 + [110.0, 110.5, 110.0, 108.5]
    d15m = _make_df(144, close_vals=close, high_vals=high, low_vals=low)
    
    # Weekly UP (Bias SELL allowed)
    d1w = _make_df(52, close_vals=[100.0]*52)
    # Daily UP (No conflict)
    d1d = _make_df(100, close_vals=[100.0]*100)
    
    with pytest.MonkeyPatch.context() as mp:
        # Mock levels: 110.0 resistance, 100.0 support
        mp.setattr(strategy, "_find_levels", lambda *_a, **_k: [{'price': 110.0, 'type': 'resistance'}, {'price': 100.0, 'type': 'support'}])
        mp.setattr(strategy, "_determine_trend", lambda df, tf: "DOWN" if tf == "Weekly" else "DOWN") # Force DOWN bias
        mp.setattr(strategy, "_calculate_atr", lambda *_a, **_k: 1.0) # ATR 1.0
        
        res = strategy._analyze_fake_breakout(d15m, d1d, d1w, "R_25")
        
        # Check if trade was identified
        # Current candle: close 109.0, open 100.0? Wait, _make_df sets open to 100.0. 
        # Body size = abs(109 - 100) = 9. ATR 1.0. 9 >= 1.2 * 1.0 is True.
        # It should trigger.
        assert res["can_trade"] is True
        assert res["signal"] == "DOWN"
        assert res["take_profit"] == 100.0 # Next level down
        assert res["stop_loss"] > 111.0 # Above highest wick
