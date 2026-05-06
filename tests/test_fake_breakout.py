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
        assert "No Fake Breakout pattern" in res["details"]["reason"]

def test_analyze_fake_breakout_success_sell(strategy):
    # Resistance at 110.0
    # Price breaks above 110.0 and then reverses below it.
    
    # M15 Data — need realistic opens so wick/body ratios work
    # Spike candles: open near close, big upper wick (wick >> body)
    # Reversal candle: big bearish body closing below 110
    n_flat = 140
    opens  = [100.0] * n_flat + [109.8, 109.9, 109.8, 110.0]
    close  = [100.0] * n_flat + [109.9, 110.0, 109.9, 108.0]  # Last reverses below 110
    high   = [101.0] * n_flat + [110.6, 110.7, 110.5, 110.0]  # Spike ~0.5-0.64% above 110
    low    = [99.0]  * n_flat + [109.7, 109.8, 109.7, 107.5]
    d15m = pd.DataFrame({'open': opens, 'high': high, 'low': low, 'close': close})
    
    # Weekly + Daily
    d1w = _make_df(52, close_vals=[100.0]*52)
    d1d = _make_df(100, close_vals=[100.0]*100)
    
    with pytest.MonkeyPatch.context() as mp:
        # Mock levels: 110.0 resistance, 100.0 support
        mp.setattr(strategy, "_find_levels", lambda *_a, **_k: [{'price': 110.0, 'type': 'resistance'}, {'price': 100.0, 'type': 'support'}])
        mp.setattr(strategy, "_determine_trend", lambda df, tf: "DOWN")
        mp.setattr(strategy, "_calculate_atr", lambda *_a, **_k: 1.0)
        
        res = strategy._analyze_fake_breakout(d15m, d1d, d1w, "R_25")
        
        # Spike candle idx -3: high=110.7, open=109.9, close=110.0
        #   upper_wick = 110.7 - 110.0 = 0.7, body = 0.1, ratio = 7.0 >= 1.5 ✓
        # Reversal candle: open=110.0, close=108.0, body=2.0 >= 1.2*ATR(1.0) ✓
        # spike_pct = (110.7-110)/110 = 0.636% within [0.05%, 0.8%] ✓
        assert res["can_trade"] is True
        assert res["signal"] == "DOWN"
        assert res["take_profit"] == 100.0  # Next level down
        assert res["stop_loss"] > 110.7     # Above highest wick (110.7 + buffer)

