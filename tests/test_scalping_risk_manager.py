import pytest
from datetime import datetime, timedelta
from scalping_risk_manager import ScalpingRiskManager
from unittest.mock import MagicMock, AsyncMock, patch

@pytest.fixture
def srm():
    return ScalpingRiskManager(user_id="test_user")

def test_scalping_rm_init(srm):
    assert srm.user_id == "test_user"
    assert srm.max_concurrent_trades > 0
    assert srm.daily_trade_count == 0

def test_scalping_rm_can_trade_success(srm):
    can, reason = srm.can_trade("R_25")
    assert can is True
    assert "passed" in reason.lower()

def test_scalping_rm_concurrent_limit(srm):
    srm.max_concurrent_trades = 1
    srm.active_trades = ["CON1"]
    can, reason = srm.can_trade("R_25")
    assert can is False
    assert "concurrent" in reason

def test_scalping_rm_cooldown(srm):
    srm.cooldown_seconds = 60
    srm.last_trade_time = datetime.now() - timedelta(seconds=10)
    can, reason = srm.can_trade("R_25")
    assert can is False
    assert "Cooldown" in reason

def test_scalping_rm_daily_loss(srm):
    srm.stake = 10.0
    srm.daily_loss_multiplier = 2.0
    srm.daily_pnl = -25.0
    can, reason = srm.can_trade("R_25")
    assert can is False
    assert "loss limit" in reason

def test_scalping_rm_record_lifecycle(srm):
    trade_info = {"contract_id": "CON1", "stake": 10.0, "symbol": "R_25"}
    srm.record_trade_open(trade_info)
    assert len(srm.active_trades) == 1
    assert srm.daily_trade_count == 1
    
    srm.record_trade_close("CON1", 5.0, "won")
    assert len(srm.active_trades) == 0
    assert srm.daily_pnl == 5.0

def test_scalping_rm_stagnation_exit(srm):
    trade_info = {
        "open_time": datetime.now() - timedelta(seconds=200),
        "stake": 10.0,
        "symbol": "R_25"
    }
    
    # Use patch to avoid polluting global config
    with patch("scalping_config.SCALPING_STAGNATION_EXIT_TIME", 150), \
         patch("scalping_config.SCALPING_STAGNATION_LOSS_PCT", 10.0):
        # Losing 20%
        should_exit, reason = srm.check_stagnation_exit(trade_info, -2.0)
        assert should_exit is True
        assert reason == "stagnation_exit"

def test_scalping_rm_trailing_profit(srm):
    trade_info = {"contract_id": "CON1", "stake": 100.0, "symbol": "R_25"}
    
    # Use patch to avoid polluting global config
    with patch("scalping_config.SCALPING_TRAIL_ACTIVATION_PCT", 10.0), \
         patch("scalping_config.SCALPING_TRAIL_TIERS", [(10.0, 5.0)]):
        
        # 1. Below activation
        should, reason, just_acts = srm.check_trailing_profit(trade_info, 5.0) # 5%
        assert should is False
        assert just_acts is False
        
        # 2. Activation
        should, reason, just_acts = srm.check_trailing_profit(trade_info, 12.0) # 12%
        assert should is False
        assert just_acts is True
        
        # 3. Increase peak to 20%
        srm.check_trailing_profit(trade_info, 20.0)
        
        # 4. Drop below floor (20% - 5% = 15%)
        should, reason, just_acts = srm.check_trailing_profit(trade_info, 14.0)
        assert should is True
        assert reason == "trailing_profit_exit"
