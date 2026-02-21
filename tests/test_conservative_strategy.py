"""
Unit tests for conservative_strategy
Tests the wrapper logic and delegation to TradingStrategy.
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from conservative_strategy import ConservativeStrategy

@pytest.fixture
def mock_trading_strategy():
    with patch("conservative_strategy.TradingStrategy") as mock:
        yield mock

def test_analyze_delegation(mock_trading_strategy):
    """Test that analyze correctly delegates to TradingStrategy."""
    strategy = ConservativeStrategy()
    
    # Mock data for all timeframes
    kwargs = {
        'data_1m': pd.DataFrame({'close': [1]}),
        'data_5m': pd.DataFrame({'close': [2]}),
        'data_1h': pd.DataFrame({'close': [3]}),
        'data_4h': pd.DataFrame({'close': [4]}),
        'data_1d': pd.DataFrame({'close': [5]}),
        'data_1w': pd.DataFrame({'close': [6]}),
        'symbol': 'R_10'
    }
    
    mock_instance = mock_trading_strategy.return_value
    mock_instance.analyze.return_value = {"signal": "UP"}
    
    result = strategy.analyze(**kwargs)
    
    assert result == {"signal": "UP"}
    mock_instance.analyze.assert_called_once_with(**kwargs)

def test_analyze_missing_data(mock_trading_strategy):
    """Test that analyze returns None if timeframe data is missing."""
    strategy = ConservativeStrategy()
    
    # Missing data_1w
    kwargs = {
        'data_1m': pd.DataFrame({'close': [1]}),
        'data_5m': pd.DataFrame({'close': [2]}),
        'data_1h': pd.DataFrame({'close': [3]}),
        'data_4h': pd.DataFrame({'close': [4]}),
        'data_1d': pd.DataFrame({'close': [5]}),
        'symbol': 'R_10'
    }
    
    result = strategy.analyze(**kwargs)
    
    assert result is None
    mock_trading_strategy.return_value.analyze.assert_not_called()

def test_metadata():
    """Test metadata methods."""
    strategy = ConservativeStrategy()
    assert strategy.get_strategy_name() == "Conservative"
    assert "1m" in strategy.get_required_timeframes()
    assert "1w" in strategy.get_required_timeframes()
    assert len(strategy.get_required_timeframes()) == 6
