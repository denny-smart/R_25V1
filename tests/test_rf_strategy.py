"""
Unit tests for risefallbot.rf_strategy
Tests triple-confirmation logic, indicator handling, and signal generation.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from risefallbot.rf_strategy import RiseFallStrategy

@pytest.fixture
def strategy():
    with patch("risefallbot.rf_strategy.rf_config") as mock_config:
        # Set default config values
        mock_config.RF_EMA_FAST = 5
        mock_config.RF_EMA_SLOW = 13
        mock_config.RF_RSI_PERIOD = 7
        mock_config.RF_RSI_OVERSOLD = 30
        mock_config.RF_RSI_OVERBOUGHT = 70
        mock_config.RF_STOCH_K_PERIOD = 5
        mock_config.RF_STOCH_D_PERIOD = 3
        mock_config.RF_STOCH_OVERSOLD = 20
        mock_config.RF_STOCH_OVERBOUGHT = 80
        mock_config.RF_MIN_BARS = 20
        mock_config.RF_DEFAULT_STAKE = 10.0
        mock_config.RF_CONTRACT_DURATION = 5
        mock_config.RF_DURATION_UNIT = "t"
        yield RiseFallStrategy()

@pytest.fixture
def sample_df():
    """Create a sample DF with enough bars."""
    return pd.DataFrame({
        "close": np.linspace(100, 110, 30),
        "high": np.linspace(101, 111, 30),
        "low": np.linspace(99, 109, 30),
        "open": np.linspace(100, 110, 30)
    })

def test_analyze_insufficient_data(strategy):
    """Test when data is shorter than min_bars."""
    df = pd.DataFrame({"close": [1, 2, 3]})
    result = strategy.analyze(data_1m=df, symbol="R_10")
    assert result is None

def test_analyze_empty_data(strategy):
    """Test with empty or None data."""
    assert strategy.analyze(data_1m=None, symbol="R_10") is None
    assert strategy.analyze(data_1m=pd.DataFrame(), symbol="R_10") is None

@patch("risefallbot.rf_strategy.calculate_ema")
@patch("risefallbot.rf_strategy.calculate_rsi")
@patch("risefallbot.rf_strategy.calculate_stochastic")
def test_analyze_call_signal(mock_stoch, mock_rsi, mock_ema, strategy, sample_df):
    """Test successful CALL signal generation."""
    # EMA Fast > EMA Slow
    mock_ema.side_effect = [
        pd.Series([10.0] * 30), # Fast
        pd.Series([9.0] * 30)   # Slow
    ]
    # RSI < 30 (oversold)
    mock_rsi.return_value = pd.Series([25.0] * 30)
    # Stoch < 20 (oversold)
    mock_stoch.return_value = (pd.Series([15.0] * 30), pd.Series([15.0] * 30))
    
    result = strategy.analyze(data_1m=sample_df, symbol="R_10")
    
    assert result is not None
    assert result["direction"] == "CALL"
    assert result["symbol"] == "R_10"
    assert result["stake"] == 10.0
    assert result["ema_fast"] == 10.0
    assert result["rsi"] == 25.0

@patch("risefallbot.rf_strategy.calculate_ema")
@patch("risefallbot.rf_strategy.calculate_rsi")
@patch("risefallbot.rf_strategy.calculate_stochastic")
def test_analyze_put_signal(mock_stoch, mock_rsi, mock_ema, strategy, sample_df):
    """Test successful PUT signal generation."""
    # EMA Fast < EMA Slow
    mock_ema.side_effect = [
        pd.Series([9.0] * 30),  # Fast
        pd.Series([10.0] * 30)  # Slow
    ]
    # RSI > 70 (overbought)
    mock_rsi.return_value = pd.Series([75.0] * 30)
    # Stoch > 80 (overbought)
    mock_stoch.return_value = (pd.Series([85.0] * 30), pd.Series([85.0] * 30))
    
    result = strategy.analyze(data_1m=sample_df, symbol="R_10")
    
    assert result is not None
    assert result["direction"] == "PUT"
    assert result["rsi"] == 75.0

@patch("risefallbot.rf_strategy.calculate_ema")
@patch("risefallbot.rf_strategy.calculate_rsi")
@patch("risefallbot.rf_strategy.calculate_stochastic")
def test_analyze_no_signal(mock_stoch, mock_rsi, mock_ema, strategy, sample_df):
    """Test case where only some conditions are met."""
    # Bullish EMA cross but RSI not oversold
    mock_ema.side_effect = [pd.Series([10.0]*30), pd.Series([9.0]*30)]
    mock_rsi.return_value = pd.Series([50.0]*30)
    mock_stoch.return_value = (pd.Series([15.0]*30), pd.Series([15.0]*30))
    
    result = strategy.analyze(data_1m=sample_df, symbol="R_10")
    assert result is None

@patch("risefallbot.rf_strategy.calculate_ema")
@patch("risefallbot.rf_strategy.calculate_rsi")
@patch("risefallbot.rf_strategy.calculate_stochastic")
def test_analyze_nan_indicator(mock_stoch, mock_rsi, mock_ema, strategy, sample_df):
    """Test handling of NaN indicator values."""
    mock_ema.side_effect = [pd.Series([np.nan]*30), pd.Series([9.0]*30)]
    mock_rsi.return_value = pd.Series([25.0]*30)
    mock_stoch.return_value = (pd.Series([15.0]*30), pd.Series([15.0]*30))
    
    assert strategy.analyze(data_1m=sample_df, symbol="R_10") is None

def test_metadata(strategy):
    """Test strategy metadata methods."""
    assert strategy.get_strategy_name() == "RiseFall"
    assert strategy.get_required_timeframes() == ["1m"]
