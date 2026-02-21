from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

import strategy as st_mod
import trade_engine as te_mod


def _df(n=40, base=100.0):
    return pd.DataFrame(
        {
            "open": [base for _ in range(n)],
            "high": [base + 0.2 for _ in range(n)],
            "low": [base - 0.2 for _ in range(n)],
            "close": [base for _ in range(n)],
        }
    )


@pytest.mark.asyncio
async def test_trade_engine_authorize_unknown_and_send_request_connection_closed(monkeypatch):
    eng = te_mod.TradeEngine("T")

    # authorize unknown payload branch
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock(return_value='{"msg_type":"authorize"}')
    eng.ws = ws
    assert await eng.authorize() is False

    # send_request connection-closed branch with reconnect failure
    class DummyClosed(Exception):
        pass

    if not hasattr(te_mod.websockets, "exceptions"):
        monkeypatch.setattr(
            te_mod.websockets,
            "exceptions",
            SimpleNamespace(ConnectionClosed=DummyClosed, ConnectionClosedError=DummyClosed),
            raising=False,
        )
    else:
        monkeypatch.setattr(te_mod.websockets.exceptions, "ConnectionClosed", DummyClosed)
        monkeypatch.setattr(te_mod.websockets.exceptions, "ConnectionClosedError", DummyClosed)
    eng.ensure_connected = AsyncMock(return_value=True)
    eng.ws = AsyncMock()
    eng.ws.send = AsyncMock(side_effect=DummyClosed("closed"))
    eng.reconnect = AsyncMock(return_value=False)
    out = await eng.send_request({"ping": 1})
    assert out["error"]["message"] == "Connection lost"

    # reconnect success + retry error
    eng.ws.send = AsyncMock(side_effect=[DummyClosed("closed"), None])
    eng.ws.recv = AsyncMock(side_effect=RuntimeError("retry fail"))
    eng.reconnect = AsyncMock(return_value=True)
    out2 = await eng.send_request({"ping": 1})
    assert "retry fail" in out2["error"]["message"]


@pytest.mark.asyncio
async def test_trade_engine_apply_limits_and_open_trade_retry_paths(monkeypatch):
    eng = te_mod.TradeEngine("T")

    # invalid entry spot branch
    assert (
        await eng.apply_tp_sl_limits(
            contract_id="1",
            tp_price=101.0,
            sl_price=99.0,
            entry_spot=0.0,
            multiplier=100,
            stake=1.0,
        )
        is False
    )

    # request exception branch in apply_tp_sl_limits
    eng.send_request = AsyncMock(side_effect=RuntimeError("limit fail"))
    assert (
        await eng.apply_tp_sl_limits(
            contract_id="1",
            tp_price=101.0,
            sl_price=99.0,
            entry_spot=100.0,
            multiplier=100,
            stake=1.0,
        )
        is False
    )

    # open_trade proposal retry exhaustion
    eng.is_connected = True
    eng.ws = SimpleNamespace(closed=False)
    eng.get_proposal = AsyncMock(side_effect=[None, None])
    out = await eng.open_trade("UP", 1.0, "R_25", max_retries=2)
    assert out is None


@pytest.mark.asyncio
async def test_trade_engine_monitor_scalping_fallback_and_exception(monkeypatch):
    eng = te_mod.TradeEngine("T")
    monkeypatch.setattr(te_mod.config, "MONITOR_INTERVAL", 0)

    # Make isinstance(..., ScalpingRiskManager) true for our dummy class
    import scalping_risk_manager as srm_mod

    class DummyScalp:
        def get_active_trade_info(self):
            # contract mismatch -> fallback should_close_trade path
            return {"contract_id": "other"}

        def check_trailing_profit(self, *_a, **_k):
            return False, "", False

        def check_stagnation_exit(self, *_a, **_k):
            return False, ""

        def should_close_trade(self, *_a, **_k):
            return {"should_close": False, "reason": "", "message": ""}

    monkeypatch.setattr(srm_mod, "ScalpingRiskManager", DummyScalp)

    # First open tick to execute fallback path; second closed with bad dates to hit duration except
    eng.get_trade_status = AsyncMock(
        side_effect=[
            {"status": "open", "is_sold": False, "profit": 0.1, "current_spot": 100.1},
            {
                "status": "",
                "is_sold": True,
                "profit": -0.2,
                "current_spot": 99.8,
                "date_start": "x",
                "sell_time": "y",
            },
        ]
    )
    out = await eng.monitor_trade("c1", {"symbol": "R_25", "entry_spot": 100.0}, DummyScalp())
    assert out is not None
    assert out["status"] == ""
    assert out["symbol"] == "R_25"

    # outer exception path
    eng.get_trade_status = AsyncMock(side_effect=RuntimeError("monitor crash"))
    out2 = await eng.monitor_trade("c2", {"symbol": "R_25", "entry_spot": 100.0}, DummyScalp())
    assert out2 is None


@pytest.mark.asyncio
async def test_trade_engine_execute_trade_monitor_none_and_cleanup():
    eng = te_mod.TradeEngine("T")
    eng.validate_symbol = MagicMock(return_value=True)
    eng.open_trade = AsyncMock(
        return_value={
            "contract_id": "c1",
            "stake": 1.0,
            "entry_spot": 100.0,
            "symbol": "R_25",
        }
    )
    eng.monitor_trade = AsyncMock(return_value=None)

    rm = SimpleNamespace(
        record_trade_open=MagicMock(),
        active_trades=[{"contract_id": "c1"}, {"contract_id": "c2"}],
    )
    out = await eng.execute_trade(
        {"signal": "UP", "symbol": "R_25", "stake": 1.0, "take_profit": 101.0, "stop_loss": 99.0},
        rm,
    )
    assert out is None
    assert len(rm.active_trades) <= 2


def test_strategy_identify_tp_sl_and_entry_trigger_down_branches(monkeypatch):
    s = st_mod.TradingStrategy()
    monkeypatch.setattr(st_mod.config, "MIN_TP_DISTANCE_PCT", 0.1, raising=False)
    s.max_sl_distance_pct = 0.5

    # DOWN path: no highs in 5m/1h/4h, fallback to daily highs
    seq = [
        ([], []),  # 5m
        ([], []),  # 1h
        ([], []),  # 4h
        ([102.0], []),  # daily fallback
    ]
    s._get_swing_points = MagicMock(side_effect=seq)
    levels = [{"price": 99.0}, {"price": 95.0}]
    tp, sl = s._identify_tp_sl_levels(levels, 100.0, "DOWN", _df(), _df(), _df(), _df())
    assert tp == 99.0
    # clamped to max distance because 102 is far for configured max_sl_distance_pct
    assert sl == pytest.approx(100.5)

    # entry trigger edge paths
    ok0, _ = s._check_entry_trigger(_df(), None, "DOWN")
    assert ok0 is False

    s._calculate_atr = MagicMock(return_value=0.0)
    ok1, reason1 = s._check_entry_trigger(_df(), 100.0, "DOWN")
    assert ok1 is False
    assert "ATR calculation failed" in reason1

    # no breakout
    s._calculate_atr = MagicMock(return_value=1.0)
    flat = _df(30, 100.0)
    ok2, reason2 = s._check_entry_trigger(flat, 100.0, "DOWN")
    assert ok2 is False
    assert "No momentum breakout" in reason2

    # deep retracement fail for DOWN
    d = _df(30, 100.0)
    d.iloc[-2] = [101.0, 101.2, 98.8, 98.9]  # breakout down
    d.iloc[-1] = [99.0, 101.5, 98.7, 99.6]  # retraces too high
    ok3, reason3 = s._check_entry_trigger(d, 100.0, "DOWN")
    assert ok3 is False
    assert "Deep retracement" in reason3


def test_strategy_find_levels_empty_and_middle_zone_boundaries():
    s = st_mod.TradingStrategy()
    assert s._find_levels(pd.DataFrame(), "1h") == []

    # exactly at boundaries should be False (strict inequalities)
    s.middle_zone_pct = 40
    assert s._is_in_middle_zone(130.0, 100.0, 200.0) is False
    assert s._is_in_middle_zone(170.0, 100.0, 200.0) is False
