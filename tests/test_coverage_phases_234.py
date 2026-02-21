import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

import data_fetcher as df_mod
import trade_engine as te_mod
import risk_manager as rm_mod
import strategy as st_mod
import risefallbot.rf_bot as rf_bot
from app.bot.runner import BotRunner, BotStatus


@pytest.mark.asyncio
async def test_phase2_data_fetcher_retry_and_timeframe_paths(monkeypatch):
    fetcher = df_mod.DataFetcher(api_token="T")

    # send_request early connection failure
    fetcher.ensure_connected = AsyncMock(return_value=False)
    out = await fetcher.send_request({"x": 1})
    assert "Failed to establish early connection" in out["error"]["message"]

    # send_request retries transient API errors then succeeds
    fetcher.ensure_connected = AsyncMock(return_value=True)
    fetcher.is_connected = True
    ws = AsyncMock()
    ws.closed = False
    ws.send = AsyncMock()
    ws.recv = AsyncMock(side_effect=[
        '{"error": {"message": "Sorry, an error occurred"}}',
        '{"ok": true}'
    ])
    fetcher.ws = ws
    monkeypatch.setattr(df_mod.config, "MAX_RETRIES", 2)
    monkeypatch.setattr(df_mod.config, "RETRY_DELAY", 0)
    res = await fetcher.send_request({"req": 1})
    assert res == {"ok": True}

    # unsupported timeframe branch
    assert await fetcher.fetch_timeframe("R_25", "2m", 10) is None

    # weekly timeframe branch + tail count
    dfd = pd.DataFrame({
        "timestamp": [1, 2, 3, 4, 5, 6, 7, 8],
        "open": [1, 1, 1, 1, 1, 1, 1, 1],
        "high": [2, 2, 2, 2, 2, 2, 2, 2],
        "low": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
        "close": [1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2],
        "datetime": pd.date_range("2024-01-01", periods=8, freq="D"),
    })
    fetcher.fetch_candles = AsyncMock(return_value=dfd)
    original_resample = fetcher._resample_to_weekly
    fetcher._resample_to_weekly = MagicMock(return_value=dfd.tail(1))
    wk = await fetcher.fetch_timeframe("R_25", "1w", 1)
    assert wk is not None and len(wk) <= 1

    # resample exception path
    fetcher._resample_to_weekly = original_resample
    bad = pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1], "timestamp": [1]})
    assert fetcher._resample_to_weekly(bad) is None


@pytest.mark.asyncio
async def test_phase2_data_fetcher_convenience_functions(monkeypatch):
    fake = MagicMock()
    fake.connect = AsyncMock(return_value=False)
    fake.disconnect = AsyncMock()
    fake.fetch_multi_timeframe_data = AsyncMock(return_value={"1m": pd.DataFrame()})
    fake.fetch_all_timeframes = AsyncMock(return_value={"1m": pd.DataFrame()})

    monkeypatch.setattr(df_mod, "DataFetcher", lambda *_a, **_k: fake)
    assert await df_mod.get_market_data("R_25") == {}
    assert await df_mod.get_all_timeframes_data("R_25") == {}
    fake.disconnect.assert_awaited()


@pytest.mark.asyncio
async def test_phase2_trade_engine_connection_and_aux_paths(monkeypatch):
    eng = te_mod.TradeEngine(api_token="T")

    # connect fails when authorize fails
    ws = AsyncMock()
    ws.closed = False
    monkeypatch.setattr(te_mod.websockets, "connect", AsyncMock(return_value=ws))
    eng.authorize = AsyncMock(return_value=False)
    eng.disconnect = AsyncMock()
    assert await eng.connect() is False
    eng.disconnect.assert_awaited()

    # send_request early connection failure
    eng.ensure_connected = AsyncMock(return_value=False)
    out = await eng.send_request({"x": 1})
    assert "Failed to establish connection" in out["error"]["message"]

    # remove_take_profit success and failure
    eng.send_request = AsyncMock(return_value={"contract_update": {"ok": 1}})
    assert await eng.remove_take_profit("123") is True
    eng.send_request = AsyncMock(return_value={"error": {"message": "nope"}})
    assert await eng.remove_take_profit("123") is False

    # close_trade invalid response branch
    eng.send_request = AsyncMock(return_value={"not_sell": 1})
    assert await eng.close_trade("1") is None


@pytest.mark.asyncio
async def test_phase2_trade_engine_monitor_and_execute_paths(monkeypatch):
    eng = te_mod.TradeEngine(api_token="T")

    # monitor direct sold/won path
    eng.get_trade_status = AsyncMock(return_value={
        "is_sold": True,
        "status": "",
        "profit": 3.0,
        "current_spot": 101.0,
        "date_start": 10,
        "sell_time": 20,
    })
    out = await eng.monitor_trade("c1", {"symbol": "R_25", "entry_spot": 100.0})
    assert out["is_sold"] is True
    assert out["duration"] == 10

    # execute_trade invalid symbol and missing tp/sl
    assert await eng.execute_trade({"signal": "UP", "symbol": "BAD"}, MagicMock()) is None
    assert await eng.execute_trade({"signal": "UP", "symbol": "R_25"}, MagicMock()) is None


@pytest.mark.asyncio
async def test_phase3_risk_manager_additional_branches(monkeypatch):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(rm_mod.config, "MAX_TRADES_PER_DAY", 10)
        mp.setattr(rm_mod.config, "COOLDOWN_SECONDS", 60)
        mp.setattr(rm_mod.config, "MAX_CONSECUTIVE_LOSSES", 3)
        mp.setattr(rm_mod.config, "DAILY_LOSS_MULTIPLIER", 5.0)
        mp.setattr(rm_mod.config, "MAX_DAILY_LOSS", 50.0)
        mp.setattr(rm_mod.config, "MAX_LOSS_PER_TRADE", 10.0)
        mp.setattr(rm_mod.config, "SYMBOLS", ["R_25", "R_50"])
        mp.setattr(rm_mod.config, "ASSET_CONFIG", {"R_25": {"multiplier": 10}, "R_50": {"multiplier": 20}})
        mp.setattr(rm_mod.config, "USE_TOPDOWN_STRATEGY", True)
        mp.setattr(rm_mod.config, "MAX_CONCURRENT_TRADES", 2)
        mp.setattr(rm_mod.config, "TOPDOWN_MIN_RR_RATIO", 1.5)
        mp.setattr(rm_mod.config, "MIN_RR_RATIO", 1.0)
        mp.setattr(rm_mod.config, "STRICT_RR_ENFORCEMENT", True)
        mp.setattr(rm_mod.config, "MAX_RISK_PCT", 10.0)
        mp.setattr(rm_mod.config, "MIN_SIGNAL_STRENGTH", 5.0)
        mp.setattr(rm_mod.config, "STAKE_LIMIT_MULTIPLIER", 1.5)
        mp.setattr(rm_mod.config, "ENABLE_BREAKEVEN_RULE", True)
        mp.setattr(rm_mod.config, "BREAKEVEN_TRIGGER_PCT", 20.0)
        mp.setattr(rm_mod.config, "BREAKEVEN_MAX_LOSS_PCT", 5.0)
        mp.setattr(rm_mod.config, "ENABLE_MULTI_TIER_TRAILING", True)
        mp.setattr(rm_mod.config, "TRAILING_STOPS", [{"name": "Tier 1", "trigger_pct": 25.0, "trail_pct": 10.0}])
        mp.setattr(rm_mod.config, "ENABLE_STAGNATION_EXIT", True)
        mp.setattr(rm_mod.config, "STAGNATION_EXIT_TIME", 300)
        mp.setattr(rm_mod.config, "STAGNATION_LOSS_PCT", 50.0)

        rm = rm_mod.RiskManager()
        rm.update_risk_settings(10.0)

        assert rm.calculate_risk_amounts({"symbol": "BAD"}, 10.0) == {}
        amts = rm.calculate_risk_amounts({"symbol": "R_25", "entry_price": 0.0, "current_price": 100.0, "stop_loss": 99.0, "take_profit": 102.0}, 10.0)
        assert amts["rr_ratio"] > 0

        ok, reason = rm.validate_trade_parameters("R_25", 1000.0)
        assert ok is False and "exceeds" in reason

        rm.record_trade_open({"symbol": "R_25", "contract_id": "c1", "direction": "UP", "stake": 10.0, "entry_price": 100.0})
        rm.cancellation_fee = 0.5
        rm.record_trade_cancelled("c1", 9.5)
        assert len(rm.active_trades) == 0

        rm.record_trade_open({"symbol": "R_25", "contract_id": "c2", "direction": "UP", "stake": 10.0, "entry_price": 100.0})
        rm.target_profit = 3.0
        rm.max_loss = 2.0
        rm.record_cancellation_expiry("c2")
        est = rm.get_exit_status("c2", 1.0)
        assert est["active"] is True

        rm.record_trade_close("c2", 1.0, "won")
        assert rm.get_exit_status("missing", 0.0) == {"active": False}
        assert rm.is_within_trading_hours() is True

        # exception branch
        bad_api = SimpleNamespace(portfolio=AsyncMock(side_effect=RuntimeError("x")))
        assert await rm.check_for_existing_positions(bad_api) is False


def _make_df(n=120, start=100.0, step=0.1):
    return pd.DataFrame({
        "open": [start + i * step for i in range(n)],
        "high": [start + i * step + 0.2 for i in range(n)],
        "low": [start + i * step - 0.2 for i in range(n)],
        "close": [start + i * step + 0.1 for i in range(n)],
    })


def test_phase3_strategy_additional_analyze_paths(monkeypatch):
    s = st_mod.TradingStrategy()
    df = _make_df()

    monkeypatch.setattr(st_mod, "calculate_adx", lambda _x: pd.Series([40] * len(df)))
    monkeypatch.setattr(st_mod, "calculate_rsi", lambda _x: pd.Series([60] * len(df)))

    import indicators

    # parabolic rejection
    monkeypatch.setattr(indicators, "detect_price_movement", lambda *_a, **_k: (1.0, 1.0, True))
    monkeypatch.setattr(indicators, "detect_consolidation", lambda *_a, **_k: (True, 1, 1))
    r = s.analyze(df, df, df, df, df, df, symbol="R_25")
    assert r["can_trade"] is False and "Parabolic" in r["details"]["reason"]

    # movement too high rejection
    monkeypatch.setattr(indicators, "detect_price_movement", lambda *_a, **_k: (99.0, 1.0, False))
    r = s.analyze(df, df, df, df, df, df, symbol="R_25")
    assert r["can_trade"] is False and "late entry rejected" in r["details"]["reason"].lower()

    # force no target path after trend alignment
    monkeypatch.setattr(indicators, "detect_price_movement", lambda *_a, **_k: (0.1, 0.1, False))
    monkeypatch.setattr(indicators, "detect_consolidation", lambda *_a, **_k: (True, 1, 1))
    monkeypatch.setattr(s, "_determine_trend", lambda *_a, **_k: "UP")
    monkeypatch.setattr(s, "_identify_tp_sl_levels", lambda *_a, **_k: (None, 95.0))
    r = s.analyze(df, df, df, df, df, df, symbol="R_25")
    assert r["can_trade"] is False and "No clear Structure Level" in r["details"]["reason"]

    # helper branch checks
    ok, msg = s._check_entry_trigger(df.tail(5), 100.0, "UP")
    assert ok is False and "ATR" in msg
    v, _, _ = s._validate_level_proximity(100.0, None, "UP")
    assert v is False


@pytest.mark.asyncio
async def test_phase4_rf_bot_lock_and_db_retry_paths(monkeypatch):
    monkeypatch.setattr(rf_bot.rf_config, "RF_ENFORCE_DB_LOCK", False)
    assert await rf_bot._acquire_session_lock("u1") is True

    monkeypatch.setattr(rf_bot.rf_config, "RF_ENFORCE_DB_LOCK", True)
    assert await rf_bot._acquire_session_lock("") is False

    # release lock exception path should not raise
    bad_supabase = MagicMock()
    bad_supabase.table.return_value.delete.return_value.eq.return_value.execute.side_effect = RuntimeError("x")
    monkeypatch.setattr("app.core.supabase.supabase", bad_supabase)
    await rf_bot._release_session_lock("u")

    # db retry all-fail path + duration conversion
    monkeypatch.setattr(rf_bot.rf_config, "RF_DB_WRITE_MAX_RETRIES", 2)
    monkeypatch.setattr(rf_bot.rf_config, "RF_DB_WRITE_RETRY_DELAY", 0)
    svc = MagicMock()
    svc.save_trade.return_value = False
    ok = await rf_bot._write_trade_to_db_with_retry(
        user_id="u",
        contract_id="c",
        symbol="R_25",
        direction="CALL",
        stake_val=1.0,
        pnl=-0.5,
        status="lost",
        closure_reason="x",
        duration=1,
        duration_unit="h",
        result={},
        settlement={},
        UserTradesService=svc,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_phase4_runner_start_stop_status_and_monitor(monkeypatch):
    r = BotRunner(account_id="u1")

    # start without stake branch
    res = await r.start_bot(stake=None)
    assert res["success"] is False and "Stake amount not configured" in res["message"]

    # stop success branch
    r.is_running = True
    r.status = BotStatus.RUNNING
    r.task = asyncio.create_task(asyncio.sleep(0))
    r.data_fetcher = SimpleNamespace(disconnect=AsyncMock())
    r.trade_engine = SimpleNamespace(disconnect=AsyncMock())
    r.telegram_bridge = SimpleNamespace(notify_bot_stopped=AsyncMock())
    monkeypatch.setattr("app.bot.runner.event_manager", SimpleNamespace(broadcast=AsyncMock()))
    out = await r.stop_bot()
    assert out["success"] is True

    # get_status with active trade info
    r.risk_manager = SimpleNamespace(active_trades=[{"contract_id": "c", "symbol": "R_25"}], get_active_trade_info=lambda: {"symbol": "R_25"})
    status = r.get_status()
    assert status["multi_asset"]["active_symbol"] == "R_25"

    # monitor active trade sold path
    r.risk_manager = SimpleNamespace(
        has_active_trade=True,
        get_active_trade_info=lambda: {
            "symbol": "R_25",
            "contract_id": "c1",
            "direction": "UP",
            "stake": 1.0,
            "entry_price": 100.0,
            "multiplier": 100,
            "open_time": datetime.now().isoformat(),
        },
        record_trade_close=MagicMock(),
    )
    r.state = SimpleNamespace(update_trade=MagicMock())
    r.trade_engine = SimpleNamespace(get_trade_status=AsyncMock(return_value={"is_sold": True, "profit": 0.5, "status": "won"}))
    r.telegram_bridge = SimpleNamespace(notify_trade_closed=AsyncMock())
    r.strategy = SimpleNamespace(get_strategy_name=lambda: "Conservative")
    await r._monitor_active_trade()
    assert r.risk_manager.record_trade_close.called
