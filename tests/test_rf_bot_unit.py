import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
import risefallbot.rf_bot as rf_bot
from risefallbot.rf_risk_manager import RiseFallRiskManager

@pytest.fixture(autouse=True)
def reset_globals():
    rf_bot._running = False
    rf_bot._bot_task = None
    rf_bot._locked_symbol = None
    if hasattr(rf_bot, "_lock_active"):
        rf_bot._lock_active = False
    yield
    rf_bot._running = False
    rf_bot._bot_task = None

@pytest.mark.asyncio
async def test_fetch_user_config_supabase():
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"deriv_api_key": "MOCK_KEY", "stake_amount": 5.0}
    ]
    
    with patch("app.core.supabase.supabase", mock_supabase), \
         patch("risefallbot.rf_bot.os.getenv", return_value=None):
        config_data = await rf_bot._fetch_user_config()
        assert config_data["api_token"] == "MOCK_KEY"
        assert config_data["stake"] == 5.0

@pytest.mark.asyncio
async def test_fetch_user_config_env():
    # Mocking to return empty list to trigger fallback
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    
    with patch("app.core.supabase.supabase", mock_supabase), \
         patch("risefallbot.rf_bot.os.getenv") as mock_getenv, \
         patch("risefallbot.rf_bot.rf_config") as mock_cfg:
        
        mock_getenv.side_effect = lambda k, d=None: "ENV_KEY" if k == "DERIV_API_TOKEN" else d
        mock_cfg.RF_DEFAULT_STAKE = 2.0
        
        config_data = await rf_bot._fetch_user_config()
        assert config_data["api_token"] == "ENV_KEY"
        assert config_data["stake"] == 2.0

@pytest.mark.asyncio
async def test_acquire_session_lock_success():
    mock_supabase = MagicMock()
    # Mock insert success
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": 1}]
    
    with patch("app.core.supabase.supabase", mock_supabase), \
         patch("risefallbot.rf_bot.rf_config.RF_ENFORCE_DB_LOCK", True):
        success = await rf_bot._acquire_session_lock("user123")
        assert success is True

@pytest.mark.asyncio
async def test_acquire_session_lock_duplicate():
    mock_supabase = MagicMock()
    # Mock insert exception for duplicate
    mock_supabase.table.return_value.insert.return_value.execute.side_effect = Exception("duplicate key")
    
    with patch("app.core.supabase.supabase", mock_supabase), \
         patch("risefallbot.rf_bot.rf_config.RF_ENFORCE_DB_LOCK", True):
        success = await rf_bot._acquire_session_lock("user123")
        assert success is False

@pytest.mark.asyncio
async def test_write_trade_to_db_retry_success():
    mock_service = MagicMock()
    mock_service.save_trade.side_effect = [False, True]
    
    with patch("risefallbot.rf_bot.rf_config.RF_DB_WRITE_RETRY_DELAY", 0.01):
        success = await rf_bot._write_trade_to_db_with_retry(
            user_id="user123", contract_id="c1", symbol="R_25", direction="CALL",
            stake_val=1.0, pnl=0.5, status="won", closure_reason="target",
            duration=1, duration_unit="m", result={}, settlement={},
            UserTradesService=mock_service
        )
        assert success is True

@pytest.mark.asyncio
async def test_process_symbol_lifecycle_failure():
    rm = RiseFallRiskManager()
    mock_em = AsyncMock()
    mock_em.broadcast = AsyncMock()
    mock_uts = MagicMock()
    mock_strategy = MagicMock()
    
    mock_df = AsyncMock()
    # Ensure it doesn't return empty df to move past line 641
    mock_df.fetch_timeframe.return_value = MagicMock(empty=False)
    
    mock_strategy.analyze.return_value = {
        "direction": "CALL", "stake": 1.0, "duration": 5, "duration_unit": "m"
    }
    
    # Trigger exception inside try block, but allow subsequent broadcasts (error, unlock) to succeed
    mock_em.broadcast.side_effect = [Exception("Lifecycle crash"), None, None, None]
    mock_te = AsyncMock()
    
    with patch("risefallbot.rf_bot.logger") as mock_logger:
        await rf_bot._process_symbol("R_25", mock_strategy, rm, mock_df, mock_te, 1.0, "user123", mock_em, mock_uts)
    
    # It should not be halted because "Lifecycle crash" is caught as a transient "lifecycle error"
    # and auto-cleared in the finally block.
    assert not rm.is_halted()

@pytest.mark.asyncio
async def test_bot_run_already_running():
    rf_bot._bot_task = MagicMock()
    rf_bot._bot_task.done.return_value = False # Bot IS running
    
    with patch("risefallbot.rf_bot._fetch_user_config") as mock_cfg:
        await rf_bot.run()
        mock_cfg.assert_not_called()

@pytest.mark.asyncio
async def test_bot_stop():
    rf_bot._running = True
    rf_bot.stop()
    assert rf_bot._running is False

@pytest.mark.asyncio
async def test_process_symbol_no_data():
    rm = RiseFallRiskManager()
    mock_df = AsyncMock()
    mock_df.fetch_timeframe.return_value = None
    
    await rf_bot._process_symbol("R_25", MagicMock(), rm, mock_df, AsyncMock(), 1.0, "user123", AsyncMock(), MagicMock())
    assert not rm.is_halted()

@pytest.mark.asyncio
async def test_process_symbol_no_signal():
    rm = RiseFallRiskManager()
    mock_df = AsyncMock()
    mock_df.fetch_timeframe.return_value = MagicMock(empty=False)
    mock_strategy = MagicMock()
    mock_strategy.analyze.return_value = None
    
    await rf_bot._process_symbol("R_25", mock_strategy, rm, mock_df, AsyncMock(), 1.0, "user123", AsyncMock(), MagicMock())
    assert not rm.is_halted()
