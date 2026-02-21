import pytest
import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock
from trade_engine import TradeEngine

@pytest.fixture
def engine():
    return TradeEngine(api_token="test_token")

@pytest.mark.asyncio
async def test_reconnect_logic(engine):
    """Test reconnection attempt logic."""
    engine.connect = AsyncMock(return_value=True)
    engine.ws = MagicMock()
    engine.ws.close = AsyncMock()
    
    with patch("trade_engine.asyncio.sleep", return_value=None):
        result = await engine.reconnect()
        assert result is True
        # reconnect_attempts increments, but since connect is mocked, it's not reset.
        # But wait, in the real code, reconnect() increments it THEN calls connect().
        # So it should be 1 if connect() doesn't reset it.
        assert engine.reconnect_attempts == 1

@pytest.mark.asyncio
async def test_authorize_success(engine):
    """Test successful authorization."""
    engine.ws = AsyncMock()
    engine.ws.recv.return_value = json.dumps({"authorize": {"loginid": "CR123"}})
    
    result = await engine.authorize()
    assert result is True

@pytest.mark.asyncio
async def test_get_proposal_multi_asset(engine):
    """Test getting proposals for different symbols."""
    engine.send_request = AsyncMock()
    engine.send_request.return_value = {
        "proposal": {"id": "p1", "ask_price": 10.0, "spot": 100.0}
    }
    
    with patch("trade_engine.config") as mock_config:
        mock_config.ASSET_CONFIG = {"R_25": {"multiplier": 100}, "R_50": {"multiplier": 200}}
        mock_config.CONTRACT_TYPE = "MULTUP"
        
        engine.asset_configs = mock_config.ASSET_CONFIG
        engine.valid_symbols = list(engine.asset_configs.keys())
        
        p1 = await engine.get_proposal("UP", 10.0, "R_25")
        assert p1["multiplier"] == 100
        
        p2 = await engine.get_proposal("UP", 10.0, "R_50")
        assert p2["multiplier"] == 200

@pytest.mark.asyncio
async def test_apply_tp_sl_limits_adjustment(engine):
    """Test SL adjustment when it exceeds stake."""
    engine.send_request = AsyncMock(return_value={"contract_update": 1})
    
    # Entry 100, SL 90 (10% drop). Multiplier 100. Stake 10.
    # Loss = (10/100) * 10 * 100 = 100 (Exceeds stake 10)
    # SL should be adjusted to 1% drop (10/100 = 0.1 -> 0.1 / 10 = 0.01)
    
    await engine.apply_tp_sl_limits(
        contract_id="123", tp_price=110.0, sl_price=90.0,
        entry_spot=100.0, multiplier=100, stake=10.0
    )
    
    # Check that send_request was called with adjusted SL amount (should be 10.0)
    args, kwargs = engine.send_request.call_args
    sent_request = args[0]
    assert sent_request["limit_order"]["stop_loss"] == 10.0

@pytest.mark.asyncio
async def test_monitor_trade_exit_tp(engine):
    """Test monitoring loop exiting on TP."""
    engine.get_trade_status = AsyncMock()
    # First check: open
    # Second check: sold/won
    engine.get_trade_status.side_effect = [
        {"status": "open", "is_sold": False, "profit": 1.0, "current_spot": 101.0},
        {"status": "won", "is_sold": True, "profit": 5.0, "current_spot": 105.0}
    ]
    
    with patch("trade_engine.config") as mock_config, \
         patch("trade_engine.asyncio.sleep", return_value=None):
        mock_config.MONITOR_INTERVAL = 0.1
        
        result = await engine.monitor_trade("c1", {"symbol": "R_25", "entry_spot": 100.0})
        assert result["status"] == "won"
        assert result["profit"] == 5.0

@pytest.mark.asyncio
async def test_close_trade(engine):
    """Test manual trade closure."""
    engine.send_request = AsyncMock(return_value={"sell": {"contract_id": 123, "sold_for": 15.0}})
    
    result = await engine.close_trade("123")
    assert result["contract_id"] == "123"
