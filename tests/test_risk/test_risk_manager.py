import pytest
from datetime import datetime, timedelta
from risk_manager import RiskManager
import config
from unittest.mock import MagicMock

@pytest.fixture
def rm():
    """Initialize RiskManager for testing"""
    return RiskManager()

def test_risk_manager_initialization(rm):
    """Test if RiskManager initializes with correct default values"""
    assert rm.max_trades_per_day == config.MAX_TRADES_PER_DAY
    assert rm.max_concurrent_trades == config.MAX_CONCURRENT_TRADES
    assert rm.consecutive_losses == 0
    assert rm.daily_pnl == 0.0
    assert len(rm.active_trades) == 0

def test_update_risk_settings(rm):
    """Test updating risk limits based on stake"""
    rm.update_risk_settings(10.0)
    assert rm.fixed_stake == 10.0
    assert rm.max_daily_loss == 10.0 * config.DAILY_LOSS_MULTIPLIER
    assert rm.max_loss_per_trade_base == 10.0

def test_can_trade_global_limit(rm):
    """Test global concurrent trades limit"""
    rm.max_concurrent_trades = 1
    rm.active_trades = [{'symbol': 'R_25'}]
    
    can_trade, reason = rm.can_trade('R_50')
    assert can_trade is False
    assert "GLOBAL LIMIT" in reason

def test_can_trade_circuit_breaker(rm):
    """Test global circuit breaker"""
    rm.consecutive_losses = rm.max_consecutive_losses
    can_trade, reason = rm.can_trade('R_25')
    assert can_trade is False
    assert "circuit breaker" in reason

def test_can_trade_daily_limit(rm):
    """Test daily trade count limit"""
    rm.max_trades_per_day = 5
    rm.trades_today = [{} for _ in range(5)]
    can_trade, reason = rm.can_trade('R_25')
    assert can_trade is False
    assert "daily trade limit" in reason

def test_can_trade_daily_loss(rm):
    """Test daily loss limit"""
    rm.max_daily_loss = 100.0
    rm.daily_pnl = -100.1
    can_trade, reason = rm.can_trade('R_25')
    assert can_trade is False
    assert "daily loss limit" in reason

def test_can_trade_cooldown(rm):
    """Test global cooldown between trades"""
    rm.cooldown_seconds = 300
    now = datetime.now()
    rm.last_trade_time = now - timedelta(seconds=100)
    can_trade, reason = rm.can_trade('R_25')
    assert can_trade is False
    assert "cooldown active" in reason
    
    rm.last_trade_time = now - timedelta(seconds=301)
    can_trade, reason = rm.can_trade('R_25')
    assert can_trade is True

def test_validate_trade_parameters_stake_limit(rm):
    """Test stake limit validation"""
    rm.fixed_stake = 10.0
    # R_25 multiplier = 160. 10 * 160 * 1.5 = 2400
    is_valid, reason = rm.validate_trade_parameters('R_25', 3000.0)
    assert is_valid is False
    assert "exceeds max" in reason

def test_calculate_risk_amounts(rm):
    """Test calculation of risk/reward amounts"""
    signal = {
        'symbol': 'R_25',
        'entry_price': 100.0,
        'stop_loss': 99.5,
        'take_profit': 102.0
    }
    amounts = rm.calculate_risk_amounts(signal, 10.0)
    assert amounts['risk_usd'] == pytest.approx(8.0)
    assert amounts['reward_usd'] == pytest.approx(32.0)
    assert amounts['rr_ratio'] == pytest.approx(4.0)

def test_record_trade_open_and_close(rm):
    """Test recording trade lifecycle"""
    trade_info = {
        'symbol': 'R_25',
        'contract_id': 'CON123',
        'direction': 'UP',
        'stake': 10.0,
        'entry_price': 100.0
    }
    
    rm.record_trade_open(trade_info)
    assert len(rm.active_trades) == 1
    
    rm.record_trade_close('CON123', 5.0, 'won')
    assert len(rm.active_trades) == 0
    assert rm.trades_today[0]['pnl'] == 5.0

def test_trailing_stop_breakeven(rm):
    """Test breakeven protection logic"""
    trade = {
        'contract_id': 'CON123',
        'breakeven_activated': None
    }
    rm.update_trailing_stop(trade, 2.5, 10.0) 
    assert trade.get('breakeven_activated') is True

def test_trailing_stop_tiers(rm):
    """Test multi-tier trailing stop logic"""
    trade = {'contract_id': 'CON123'}
    rm.update_trailing_stop(trade, 3.5, 10.0) 
    assert trade.get('trail_tier_name') == 'Initial Lock'
    
    rm.update_trailing_stop(trade, 4.5, 10.0) 
    assert trade.get('trail_tier_name') == 'Big Winner'

def test_should_close_stagnation(rm):
    """Test stagnation exit check"""
    trade = {
        'symbol': 'R_25',
        'contract_id': 'CON123',
        'timestamp': datetime.now() - timedelta(seconds=1000),
        'stake': 10.0
    }
    rm.active_trades = [trade]
    res = rm.should_close_trade('CON123', -2.0, 98.0, 99.0)
    assert res['should_close'] is True
    assert res['reason'] == 'stagnation_exit'

def test_reset_daily_stats(rm):
    """Test resetting stats on a new day"""
    rm.current_date = datetime.now().date() - timedelta(days=1)
    rm.daily_pnl = 100.0
    rm.trades_today = [{'symbol': 'R_25', 'pnl': 100.0}]
    
    rm.reset_daily_stats()
    assert rm.daily_pnl == 0.0
    assert len(rm.trades_today) == 0
