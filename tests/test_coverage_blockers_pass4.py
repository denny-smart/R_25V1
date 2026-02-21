import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

import data_fetcher as df_mod
import risefallbot.rf_bot as rf_bot
import strategy as st_mod
import trade_engine as te_mod


def _df(n=80, start=100.0, step=0.1):
    return pd.DataFrame(
        {
            "open": [start + i * step for i in range(n)],
            "high": [start + i * step + 0.2 for i in range(n)],
            "low": [start + i * step - 0.2 for i in range(n)],
            "close": [start + i * step + 0.1 for i in range(n)],
            "timestamp": [1700000000 + i * 60 for i in range(n)],
            "datetime": pd.date_range("2025-01-01", periods=n, freq="D"),
        }
    )


@pytest.mark.asyncio
async def test_trade_engine_scalping_monitor_branch(monkeypatch):
    eng = te_mod.TradeEngine("T")
    eng.remove_take_profit = AsyncMock(return_value=True)
    eng.close_trade = AsyncMock(return_value={"sold_for": 1.1})

    statuses = [
        {"status": "open", "is_sold": False, "profit": 1.0, "current_spot": 101.0},
        {
            "status": "won",
            "is_sold": True,
            "profit": 1.2,
            "current_spot": 101.2,
            "date_start": 10,
            "sell_time": 20,
        },
    ]
    eng.get_trade_status = AsyncMock(side_effect=lambda _cid: statuses.pop(0))

    class DummyScalp:
        def get_active_trade_info(self):
            return {"contract_id": "c1"}

        def check_trailing_profit(self, *_args, **_kwargs):
            return True, "trail hit", True

        def check_stagnation_exit(self, *_args, **_kwargs):
            return False, ""

        def should_close_trade(self, *_args, **_kwargs):
            return {"should_close": False, "reason": "", "message": ""}

    import scalping_risk_manager as srm_mod

    monkeypatch.setattr(srm_mod, "ScalpingRiskManager", DummyScalp)
    monkeypatch.setattr(te_mod.config, "MONITOR_INTERVAL", 0)

    out = await eng.monitor_trade("c1", {"symbol": "R_25", "entry_spot": 100.0}, DummyScalp())
    assert out is not None
    assert out["exit_reason"] == "trail hit"
    eng.remove_take_profit.assert_awaited()


@pytest.mark.asyncio
async def test_trade_engine_remove_tp_and_status_sold():
    eng = te_mod.TradeEngine("T")
    eng.send_request = AsyncMock(return_value={"contract_update": {"status": 1}})
    assert await eng.remove_take_profit("77") is True

    eng.send_request = AsyncMock(
        return_value={"proposal_open_contract": {"is_sold": 1, "profit": 0.0, "status": ""}}
    )
    s = await eng.get_trade_status("c77")
    assert s["status"] == "sold"


def test_strategy_proximity_and_middle_zone_edges(monkeypatch):
    s = st_mod.TradingStrategy()
    monkeypatch.setattr(st_mod.config, "MAX_ENTRY_DISTANCE_PCT", 1.0, raising=False)

    ok1, reason1, _ = s._validate_level_proximity(100.0, 99.0, "DOWN", symbol="R_25")
    assert ok1 is False
    assert "above level" in reason1

    ok2, reason2, _ = s._validate_level_proximity(95.0, 100.0, "DOWN", symbol="R_25")
    assert ok2 is False
    assert "too far from level" in reason2

    assert s._is_in_middle_zone(100.0, None, 110.0) is False
    assert s._is_in_middle_zone(100.0, 100.0, 100.0) is False


@pytest.mark.asyncio
async def test_data_fetcher_helpers_and_resample_branches(monkeypatch):
    f = df_mod.DataFetcher("T")
    assert await f.fetch_timeframe("R_25", "bad_tf", 10) is None

    # resample exception path (missing datetime column/index handling)
    bad_df = pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1], "timestamp": [1]})
    assert f._resample_to_weekly(bad_df) is None

    # get_market_data connect false
    fake1 = SimpleNamespace(
        connect=AsyncMock(return_value=False),
        disconnect=AsyncMock(),
        fetch_multi_timeframe_data=AsyncMock(return_value={}),
    )
    monkeypatch.setattr(df_mod, "DataFetcher", lambda *_a, **_k: fake1)
    out1 = await df_mod.get_market_data("R_25")
    assert out1 == {}
    fake1.disconnect.assert_awaited()

    # get_all_timeframes_data success
    fake2 = SimpleNamespace(
        connect=AsyncMock(return_value=True),
        disconnect=AsyncMock(),
        fetch_all_timeframes=AsyncMock(return_value={"1m": pd.DataFrame({"x": [1]})}),
    )
    monkeypatch.setattr(df_mod, "DataFetcher", lambda *_a, **_k: fake2)
    out2 = await df_mod.get_all_timeframes_data("R_50")
    assert "1m" in out2
    fake2.disconnect.assert_awaited()


@pytest.mark.asyncio
async def test_rf_bot_session_lock_and_db_retry_paths(monkeypatch):
    monkeypatch.setattr(rf_bot.rf_config, "RF_ENFORCE_DB_LOCK", False, raising=False)
    assert await rf_bot._acquire_session_lock("u1") is True

    monkeypatch.setattr(rf_bot.rf_config, "RF_ENFORCE_DB_LOCK", True, raising=False)
    assert await rf_bot._acquire_session_lock("") is False

    saver = MagicMock()
    saver.save_trade.side_effect = [Exception("db down"), False, True]
    monkeypatch.setattr(rf_bot.rf_config, "RF_DB_WRITE_MAX_RETRIES", 3, raising=False)
    monkeypatch.setattr(rf_bot.rf_config, "RF_DB_WRITE_RETRY_DELAY", 0, raising=False)

    ok = await rf_bot._write_trade_to_db_with_retry(
        user_id="u1",
        contract_id="c1",
        symbol="R_25",
        direction="CALL",
        stake_val=1.0,
        pnl=0.5,
        status="win",
        closure_reason="expiry",
        duration=1,
        duration_unit="h",
        result={"buy_price": 1.0},
        settlement={"sell_price": 1.5},
        UserTradesService=saver,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_rf_bot_run_no_token_early_return(monkeypatch):
    rf_bot._bot_task = None
    monkeypatch.setattr(rf_bot, "_fetch_user_config", AsyncMock(return_value={"api_token": None, "stake": 1.0}))
    await rf_bot.run(stake=None, api_token=None, user_id="u1")

