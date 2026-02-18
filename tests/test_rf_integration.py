"""
Smoke test: Rise/Fall BotManager integration (end-to-end)

Tests the FULL control flow:
  1. BotManager.start_bot(strategy_name="RiseFall") → routes to rf_bot.run()
  2. BotManager.get_status() → shows RF bot running
  3. BotManager.stop_bot() → rf_bot.stop() + task cancel
  4. BotManager.get_status() → shows stopped

All external I/O (Supabase, Deriv WebSocket) is mocked.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_supabase():
    """Mock the Supabase client for profile lookups."""
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.single.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{
        "deriv_api_key": "TEST_TOKEN_123",
        "stake_amount": 2.50,
        "active_strategy": "RiseFall",
    }])

    mock_client = MagicMock()
    mock_client.table.return_value = mock_table
    return mock_client


@pytest.fixture
def bot_manager():
    """Fresh BotManager instance per test."""
    from app.bot.manager import BotManager
    return BotManager(max_concurrent_bots=5)


# ---------------------------------------------------------------------------
# Test 1: Start / Status / Stop lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_risefall_start_status_stop(bot_manager, mock_supabase):
    """Full lifecycle: start → check running → stop → check stopped."""

    user_id = "test-user-001"

    # Mock: BotManager._get_user_strategy returns "RiseFall"
    # Mock: rf_bot.run so it doesn't actually connect to Deriv
    async def fake_rf_run(stake=None, api_token=None):
        """Simulate rf_bot.run() — just loop until _running is False."""
        import risefallbot.rf_bot as bot_mod
        bot_mod._running = True
        while bot_mod._running:
            await asyncio.sleep(0.1)

    with patch("risefallbot.rf_bot.run", side_effect=fake_rf_run) as mock_run, \
         patch("risefallbot.rf_bot._fetch_user_config", new_callable=AsyncMock) as mock_cfg:

        mock_cfg.return_value = {"api_token": "TEST_TOKEN", "stake": 2.50}

        # ---- START ----
        result = await bot_manager.start_bot(
            user_id=user_id,
            api_token="TEST_TOKEN_123",
            stake=2.50,
            strategy_name="RiseFall"
        )
        print(f"\n[START] result = {result}")
        assert result["success"] is True, f"Start failed: {result}"
        assert "Rise/Fall" in result["message"]

        # Let the task spin up
        await asyncio.sleep(0.3)

        # ---- STATUS (running) ----
        status = bot_manager.get_status(user_id)
        print(f"[STATUS] = {status}")
        assert status["is_running"] is True
        assert status["status"] == "running"

        # ---- STOP ----
        stop_result = await bot_manager.stop_bot(user_id)
        print(f"[STOP] result = {stop_result}")
        assert stop_result["success"] is True

        # ---- STATUS (stopped) ----
        status_after = bot_manager.get_status(user_id)
        print(f"[STATUS AFTER STOP] = {status_after}")
        assert status_after["is_running"] is False


# ---------------------------------------------------------------------------
# Test 2: Double start is rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_risefall_double_start_rejected(bot_manager):
    """Starting RF bot twice should return success=False."""

    user_id = "test-user-002"

    async def fake_rf_run(stake=None, api_token=None):
        import risefallbot.rf_bot as bot_mod
        bot_mod._running = True
        while bot_mod._running:
            await asyncio.sleep(0.1)

    with patch("risefallbot.rf_bot.run", side_effect=fake_rf_run):

        # First start
        r1 = await bot_manager.start_bot(
            user_id=user_id, api_token="T", stake=1.0, strategy_name="RiseFall"
        )
        assert r1["success"] is True
        await asyncio.sleep(0.2)

        # Second start — should be rejected
        r2 = await bot_manager.start_bot(
            user_id=user_id, api_token="T", stake=1.0, strategy_name="RiseFall"
        )
        print(f"\n[DOUBLE START] r2 = {r2}")
        assert r2["success"] is False
        assert "already running" in r2["message"]

        # Cleanup
        await bot_manager.stop_bot(user_id)


# ---------------------------------------------------------------------------
# Test 3: Stop when not running
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_risefall_stop_when_not_running(bot_manager):
    """Stopping a non-existent RF bot returns not-running message."""
    result = await bot_manager.stop_bot("nobody")
    print(f"\n[STOP NOT RUNNING] = {result}")
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Test 4: stop_all cancels RF tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stop_all_includes_rf(bot_manager):
    """BotManager.stop_all() should also cancel RF tasks."""

    user_id = "test-user-003"

    async def fake_rf_run(stake=None, api_token=None):
        import risefallbot.rf_bot as bot_mod
        bot_mod._running = True
        while bot_mod._running:
            await asyncio.sleep(0.1)

    with patch("risefallbot.rf_bot.run", side_effect=fake_rf_run):
        await bot_manager.start_bot(
            user_id=user_id, api_token="T", stake=1.0, strategy_name="RiseFall"
        )
        await asyncio.sleep(0.2)

        # Confirm running
        assert bot_manager.get_status(user_id)["is_running"] is True

        # stop_all
        await bot_manager.stop_all()

        # RF task should be gone
        assert user_id not in bot_manager._rf_tasks
        print("\n[STOP ALL] RF task cleaned up ✅")


# ---------------------------------------------------------------------------
# Test 5: rf_bot.run receives correct params
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rf_bot_receives_user_params(bot_manager):
    """Verify rf_bot.run() is called with the user's stake and api_token."""

    captured = {}

    async def capture_rf_run(stake=None, api_token=None):
        captured["stake"] = stake
        captured["api_token"] = api_token
        # Return immediately (don't loop)

    with patch("risefallbot.rf_bot.run", side_effect=capture_rf_run):
        await bot_manager.start_bot(
            user_id="test-user-004",
            api_token="MY_SECRET_TOKEN",
            stake=5.75,
            strategy_name="RiseFall"
        )
        await asyncio.sleep(0.2)

    print(f"\n[PARAMS] captured = {captured}")
    assert captured["stake"] == 5.75
    assert captured["api_token"] == "MY_SECRET_TOKEN"


# ---------------------------------------------------------------------------
# Test 6: _fetch_user_config reads from Supabase
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_user_config_from_supabase(mock_supabase):
    """_fetch_user_config reads deriv_api_key and stake_amount from profiles."""

    with patch("risefallbot.rf_bot.os.getenv", return_value=None):  # No env fallback
        with patch.dict("sys.modules", {"app.core.supabase": MagicMock(supabase=mock_supabase)}):
            from risefallbot.rf_bot import _fetch_user_config
            config = await _fetch_user_config()

    print(f"\n[CONFIG] = {config}")
    assert config["api_token"] == "TEST_TOKEN_123"
    assert config["stake"] == 2.50
