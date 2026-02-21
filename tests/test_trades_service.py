"""
Unit tests for app.services.trades_service
Tests trade persistence, history fetching, and statistics calculation with Supabase and Cache mocking.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from app.services.trades_service import UserTradesService

@pytest.fixture
def mock_supabase():
    with patch("app.services.trades_service.supabase") as mock:
        yield mock

@pytest.fixture
def mock_cache():
    with patch("app.services.trades_service.cache") as mock:
        yield mock

def test_save_trade_success(mock_supabase, mock_cache):
    """Test successful trade save path."""
    user_id = "user123"
    trade_data = {
        "contract_id": 12345,
        "symbol": "R_10",
        "signal": "UP",
        "stake": 10.0,
        "entry_price": 100.0,
        "exit_price": 105.0,
        "profit": 5.0,
        "status": "won",
        "timestamp": datetime(2023, 1, 1, 10, 0, 0)
    }
    
    # Mock Supabase response
    mock_response = MagicMock()
    mock_response.data = [{"id": 1}]
    mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_response
    
    result = UserTradesService.save_trade(user_id, trade_data)
    
    assert result == {"id": 1}
    # Verify Supabase call
    mock_supabase.table.assert_called_with("trades")
    
    # Verify cache invalidation
    mock_cache.delete_pattern.assert_called_with(f"trades:{user_id}:*")
    mock_cache.delete.assert_called_with(f"stats:{user_id}")

def test_save_trade_missing_fields(mock_supabase, mock_cache):
    """Test save_trade with missing required fields."""
    user_id = "user123"
    # Missing contract_id
    trade_data = {"symbol": "R_10", "signal": "UP"}
    
    result = UserTradesService.save_trade(user_id, trade_data)
    
    assert result is None
    mock_supabase.table.assert_not_called()

def test_save_trade_exception(mock_supabase, mock_cache):
    """Test save_trade when Supabase fails."""
    user_id = "user123"
    trade_data = {"contract_id": 1, "symbol": "R_10", "signal": "UP"}
    
    mock_supabase.table.side_effect = Exception("DB Error")
    
    result = UserTradesService.save_trade(user_id, trade_data)
    
    assert result is None

def test_get_user_trades_cache_hit(mock_supabase, mock_cache):
    """Test fetching trades from cache."""
    user_id = "user123"
    cached_trades = [{"id": 1, "symbol": "R_10"}]
    mock_cache.get.return_value = cached_trades
    
    result = UserTradesService.get_user_trades(user_id)
    
    assert result == cached_trades
    mock_supabase.table.assert_not_called()

def test_get_user_trades_cache_miss(mock_supabase, mock_cache):
    """Test fetching trades from DB on cache miss."""
    user_id = "user123"
    mock_cache.get.return_value = None
    
    db_trades = [{"id": 1, "symbol": "R_10"}]
    mock_response = MagicMock()
    mock_response.data = db_trades
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_response
    
    result = UserTradesService.get_user_trades(user_id, limit=10)
    
    assert result == db_trades
    # Verify cache set
    mock_cache.set.assert_called()

def test_get_user_stats_cache_hit(mock_supabase, mock_cache):
    """Test fetching stats from cache."""
    user_id = "user123"
    cached_stats = {"total_trades": 10, "win_rate": 60.0}
    mock_cache.get.return_value = cached_stats
    
    result = UserTradesService.get_user_stats(user_id)
    
    assert result == cached_stats
    mock_supabase.table.assert_not_called()

def test_get_user_stats_calculation(mock_supabase, mock_cache):
    """Test stats calculation from trade history."""
    user_id = "user123"
    mock_cache.get.return_value = None
    
    trades = [
        {"profit": 10.0},  # Win
        {"profit": -5.0},  # Loss
        {"profit": 15.0},  # Win
        {"profit": None},   # Invalid (ignored)
    ]
    mock_response = MagicMock()
    mock_response.data = trades
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
    
    stats = UserTradesService.get_user_stats(user_id)
    
    assert stats["total_trades"] == 4
    assert stats["winning_trades"] == 2
    assert stats["losing_trades"] == 1
    assert stats["win_rate"] == 50.0  # (2 / 4) * 100
    assert stats["total_pnl"] == 20.0 # 10 - 5 + 15
    assert stats["avg_win"] == 12.5  # (10 + 15) / 2
    assert stats["avg_loss"] == 5.0
    assert stats["largest_win"] == 15.0
    assert stats["largest_loss"] == 5.0
    assert stats["profit_factor"] == 5.0 # 25 / 5

def test_get_user_stats_no_trades(mock_supabase, mock_cache):
    """Test stats calculation with no trades."""
    user_id = "user123"
    mock_cache.get.return_value = None
    
    mock_response = MagicMock()
    mock_response.data = []
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
    
    stats = UserTradesService.get_user_stats(user_id)
    
    assert stats["total_trades"] == 0
    assert stats["win_rate"] == 0.0
    assert stats["total_pnl"] == 0.0

def test_get_user_stats_profit_factor_zero_loss(mock_supabase, mock_cache):
    """Test profit factor when there are only wins (no losses)."""
    user_id = "user123"
    mock_cache.get.return_value = None
    
    trades = [{"profit": 10.0}, {"profit": 20.0}]
    mock_response = MagicMock()
    mock_response.data = trades
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
    
    stats = UserTradesService.get_user_stats(user_id)
    
    assert stats["losing_trades"] == 0
    assert stats["profit_factor"] == 0.0 # Per implementation logic (safety)

def test_get_user_stats_exception(mock_supabase, mock_cache):
    """Test stats calculation error fallback."""
    user_id = "user123"
    mock_cache.get.return_value = None
    mock_supabase.table.side_effect = Exception("DB Fail")
    
    stats = UserTradesService.get_user_stats(user_id)
    
    assert stats["total_trades"] == 0
    assert stats["win_rate"] == 0.0
