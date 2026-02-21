import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
import json

from app.schemas.auth import UserLogin, UserRegister, Token, TokenData, User, UserResponse
from app.bot.runner import BotRunner, BotStatus
from app.bot.events import EventManager
from app.ws.live import extract_user_id_from_token, websocket_live
from app.bot.manager import BotManager
from app.bot.state import BotState
from fastapi import WebSocketDisconnect

def create_mock_bot():
    """Helper to create a bot mock with async methods"""
    bot = MagicMock()
    bot.start_bot = AsyncMock(return_value={"success": True})
    bot.stop_bot = AsyncMock(return_value={"success": True})
    bot.restart_bot = AsyncMock(return_value={"success": True})
    bot.get_status.return_value = {"status": "idle"}
    bot.is_running = False
    return bot

# --- app.schemas.auth Tests ---
def test_auth_schemas():
    login = UserLogin(username="testuser", password="password123")
    assert login.username == "testuser"
    register = UserRegister(username="testuser", password="password123", email="test@example.com")
    assert register.email == "test@example.com"
    token = Token(access_token="abc", token_type="bearer")
    assert token.token_type == "bearer"
    token_data = TokenData(username="testuser")
    assert token_data.username == "testuser"
    user = User(username="testuser", email="test@example.com", is_active=True)
    assert user.is_active is True
    user_resp = UserResponse(user=user, token=token)
    assert user_resp.user.username == "testuser"

# --- app.bot.events Tests ---
@pytest.mark.asyncio
async def test_event_manager():
    em = EventManager()
    mock_handler = AsyncMock()
    em.register("test_event", mock_handler)
    await em.broadcast({"type": "test_event", "data": "payload"})
    mock_handler.assert_called_once_with({"type": "test_event", "data": "payload"})
    em.unregister("test_event", mock_handler)
    em.unregister("non_existent", lambda x: x)
    
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()
    await em.connect(mock_ws, user_id="user123")
    assert em.active_connections[mock_ws] == "user123"
    em.disconnect(mock_ws)
    assert mock_ws not in em.active_connections

@pytest.mark.asyncio
async def test_event_manager_broadcast_ws():
    em = EventManager()
    mock_ws1 = AsyncMock()
    mock_ws1.send_json = AsyncMock()
    em.active_connections[mock_ws1] = "user1"
    em.active_connections[AsyncMock()] = None
    
    await em.broadcast({"type": "msg", "account_id": "user1", "text": "hello"})
    mock_ws1.send_json.assert_called_once()

@pytest.mark.asyncio
async def test_event_manager_errors():
    em = EventManager()
    mock_ws = AsyncMock()
    mock_ws.send_json.side_effect = RuntimeError("Failure")
    em.active_connections[mock_ws] = "user1"
    await em._send_message(mock_ws, {"m": 1})
    assert mock_ws not in em.active_connections
    
    def fail_handler(e): raise Exception("Fail")
    await em._call_handler(fail_handler, {})

# --- app.ws.live Tests ---
@pytest.mark.asyncio
async def test_websocket_live_cases():
    mock_ws = AsyncMock()
    mock_ws.headers = {"sec-websocket-protocol": "t1, t2"}
    mock_ws.receive_text.side_effect = ["hello", asyncio.TimeoutError(), WebSocketDisconnect()]
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock()
    mock_ws.close = AsyncMock()
    
    with patch("app.core.settings.settings") as mock_settings, \
         patch("app.ws.live.event_manager") as mock_em, \
         patch("app.ws.live.bot_manager") as mock_bm, \
         patch("app.ws.live.extract_user_id_from_token", return_value=None):
        
        mock_settings.WS_REQUIRE_AUTH = True
        mock_em.connect = AsyncMock()
        mock_em.disconnect = MagicMock()
        
        await websocket_live(mock_ws)
        mock_ws.close.assert_called()
        
        mock_settings.WS_REQUIRE_AUTH = False
        mock_bm.get_bot.return_value = MagicMock()
        await websocket_live(mock_ws)
        mock_em.connect.assert_called()

# --- app.bot.manager Tests ---
@pytest.mark.asyncio
async def test_bot_manager_robust():
    bm = BotManager()
    
    # Strategy Switch
    old_bot = create_mock_bot()
    old_bot.is_running = True
    old_bot.strategy.get_strategy_name.return_value = "Conservative"
    
    new_bot = create_mock_bot()
    
    fake_class = MagicMock()
    fake_class.__name__ = "FakeStrategyClass"
    fake_risk_class = MagicMock()
    fake_risk_class.__name__ = "FakeRiskManagerClass"

    with patch.object(bm, "get_bot", side_effect=[old_bot, new_bot]), \
         patch("app.bot.manager.BotManager._get_user_strategy", new_callable=AsyncMock, return_value="Scalping"), \
         patch("strategy_registry.get_strategy", return_value=(fake_class, fake_risk_class)):
        
        bm._bots["user123"] = old_bot
        result = await bm.start_bot("user123", strategy_name="Scalping")
        assert result["success"] is True
        old_bot.stop_bot.assert_called()
    
    # Restart
    mock_restart_bot = create_mock_bot()
    mock_restart_bot.is_running = True
    bm._bots["u1"] = mock_restart_bot
    with patch.object(bm, "get_bot", return_value=mock_restart_bot):
        await bm.restart_bot("u1")
        mock_restart_bot.restart_bot.assert_called()
    
    # Max concurrent
    bm.max_concurrent_bots = 1
    busy_bot = create_mock_bot()
    busy_bot.is_running = True
    bm._bots = {"busy": busy_bot}
    resp = await bm.start_bot("u3", strategy_name="Conservative")
    assert "Maximum concurrent" in resp["message"]

# --- app.bot.state Tests ---
def test_bot_state_basics():
    state = BotState()
    state.update_status("running")
    state.update_balance(50.5)
    state.add_trade({"contract_id": "abc"})
    assert state.balance == 50.5
    assert len(state.get_active_trades()) == 1
    state.update_statistics({"total_trades": 5})
    assert state.get_statistics()["total_trades"] == 5

# --- app.bot.runner Tests ---
def test_bot_runner_minimal_init():
    strategy = MagicMock()
    risk = MagicMock()
    # Simply check that BotRunner can be instantiated and has correct initial status
    runner = BotRunner("user_test", strategy, risk)
    assert runner.status == BotStatus.STOPPED
    assert not runner.is_running
