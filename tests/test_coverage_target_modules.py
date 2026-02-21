import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

import config as cfg
import indicators as ind
import main as main_mod
import risefallbot.rf_trade_engine as rf_eng_mod
from risefallbot.rf_trade_engine import RFTradeEngine


def _ohlc(n=120):
    return pd.DataFrame({
        "open": np.array([100 + i * 0.1 for i in range(n)], dtype=float),
        "high": np.array([100.3 + i * 0.1 for i in range(n)], dtype=float),
        "low": np.array([99.7 + i * 0.1 for i in range(n)], dtype=float),
        "close": np.array([100.1 + i * 0.1 for i in range(n)], dtype=float),
    })


def test_config_utils_and_validation_branches(monkeypatch):
    assert cfg.get_multiplier("R_25") == cfg.ASSET_CONFIG["R_25"]["multiplier"]
    with pytest.raises(ValueError):
        cfg.get_multiplier("BAD")
    with pytest.raises(ValueError):
        cfg.get_asset_info("BAD")

    syms = cfg.get_all_symbols()
    syms.append("X")
    assert "X" not in cfg.SYMBOLS

    # Force multiple validation errors
    monkeypatch.setattr(cfg, "FIXED_STAKE", -1, raising=False)
    monkeypatch.setattr(cfg, "MIN_RR_RATIO", 0.5, raising=False)
    monkeypatch.setattr(cfg, "TOPDOWN_MIN_RR_RATIO", 2.5, raising=False)
    monkeypatch.setattr(cfg, "EXIT_STRATEGY", "OTHER", raising=False)
    monkeypatch.setattr(cfg, "MAX_TRADE_DURATION", 10, raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", ["R_25", "R_25"], raising=False)
    with pytest.raises(ValueError):
        cfg.validate_config()


def test_config_topdown_validation_branches(monkeypatch):
    monkeypatch.setattr(cfg, "USE_TOPDOWN_STRATEGY", True, raising=False)
    monkeypatch.setattr(cfg, "MOMENTUM_CLOSE_THRESHOLD", 5.0, raising=False)
    monkeypatch.setattr(cfg, "WEAK_RETEST_MAX_PCT", 5, raising=False)
    monkeypatch.setattr(cfg, "MIDDLE_ZONE_PCT", 70, raising=False)
    monkeypatch.setattr(cfg, "LEVEL_PROXIMITY_PCT", 2.0, raising=False)
    monkeypatch.setattr(cfg, "TOPDOWN_MIN_RR_RATIO", 0.5, raising=False)
    monkeypatch.setattr(cfg, "TOPDOWN_MAX_SL_DISTANCE_PCT", 3.0, raising=False)
    monkeypatch.setattr(cfg, "SWING_LOOKBACK", 3, raising=False)
    monkeypatch.setattr(cfg, "MIN_SWING_WINDOW", 1, raising=False)
    with pytest.raises(ValueError):
        cfg.validate_topdown_config()


def test_indicators_additional_branches():
    df = _ohlc(200)
    # Stable guard branches (avoid heavy reductions that can be flaky when numpy is reloaded)
    assert ind.get_trend_direction(df.head(10)) == "SIDEWAYS"
    missing_close = pd.DataFrame({
        "open": [1.0] * 120,
        "high": [1.0] * 120,
        "low": [1.0] * 120,
        "sma_100": [1.0] * 120,
    })
    assert ind.get_trend_direction(missing_close) == "SIDEWAYS"

    # Candle helper bounds
    assert ind.is_bullish_candle(df, -1) is False
    assert ind.is_bearish_candle(df, 9999) is False
    assert ind.get_candle_body(df, -1) == 0.0
    assert ind.get_candle_range(df, 9999) == 0.0

    # Price movement insufficient data
    assert ind.detect_price_movement(df.head(5), lookback=20) == (0.0, 0.0, False)

    # Consolidation insufficient data
    is_cons, _, _ = ind.detect_consolidation(df.head(5), lookback=20)
    assert is_cons is False

    # Exhaustion branches
    ex, reason = ind.detect_exhaustion(df.head(5), 80.0, 100.0, "UP")
    assert ex is False and "Insufficient data" in reason


@pytest.mark.asyncio
async def test_rf_trade_engine_additional_branches(monkeypatch):
    eng = RFTradeEngine(api_token="T", app_id="1089")

    # _send with ws absent
    eng.ws = None
    assert await eng._send({"x": 1}) is None

    # _send timeout path
    ws = AsyncMock()
    ws.open = True

    async def _timeout_recv():
        raise asyncio.TimeoutError()

    ws.recv = _timeout_recv
    ws.send = AsyncMock()
    eng.ws = ws
    assert await eng._send({"x": 1}) is None

    # authorize fail path
    eng._send = AsyncMock(return_value={"error": {"message": "bad"}})
    assert await eng._authorize() is False

    # ghost check: no attempt info
    rf_eng_mod._last_buy_attempt.clear()
    assert await eng._check_for_ghost_contract("R_25", "CALL") is None

    # ghost check: ensure_connected false
    rf_eng_mod._last_buy_attempt["R_25"] = {"direction": "CALL", "timestamp": datetime.now()}
    eng.ensure_connected = AsyncMock(return_value=False)
    assert await eng._check_for_ghost_contract("R_25", "CALL") is None

    # wait_for_result manual close branch
    eng.ensure_connected = AsyncMock(return_value=True)
    eng._flush_stale_messages = AsyncMock(return_value=0)
    ws2 = AsyncMock()
    ws2.open = True
    ws2.send = AsyncMock()
    msgs = [
        json.dumps({
            "proposal_open_contract": {
                "contract_id": "c1",
                "is_sold": 1,
                "is_expired": 0,
                "profit": -0.5,
                "sell_price": 0.5,
            },
            "subscription": {"id": "sub1"},
        })
    ]

    async def _recv_once():
        return msgs.pop(0)

    ws2.recv = _recv_once
    eng.ws = ws2
    res = await eng.wait_for_result("c1", stake=1.0)
    assert res["closure_type"] == "manual"
    assert res["status"] == "loss"


@pytest.mark.asyncio
async def test_main_additional_branches(monkeypatch):
    bot = main_mod.TradingBot()

    # analyze_asset legacy missing data branch
    bot.data_fetcher = SimpleNamespace(fetch_multi_timeframe_data=AsyncMock(return_value={"1m": pd.DataFrame()}))
    bot.strategy = SimpleNamespace(analyze=MagicMock(return_value={"can_trade": False}))
    monkeypatch.setattr(main_mod.config, "USE_TOPDOWN_STRATEGY", False)
    assert await bot.analyze_asset("R_25") is None

    # scan_all_assets exception result branch
    bot.symbols = ["R_25"]
    bot.analyze_asset = AsyncMock(return_value=RuntimeError("x"))
    out = await bot.scan_all_assets()
    assert out == []

    # trading_cycle blocked by can_trade
    bot.risk_manager = SimpleNamespace(can_trade=lambda: (False, "cooldown"))
    bot.scan_all_assets = AsyncMock(return_value=[])
    await bot.trading_cycle()

    # trading_cycle topdown rejects low rr
    bot.risk_manager = SimpleNamespace(can_trade=lambda: (True, "ok"), get_statistics=lambda: {"win_rate": 0, "total_pnl": 0, "trades_today": 0})
    bot.scan_all_assets = AsyncMock(return_value=[{"symbol": "R_25", "signal": "UP", "take_profit": 101, "stop_loss": 99, "entry_price": 100, "risk_reward_ratio": 0.2}])
    monkeypatch.setattr(main_mod.config, "USE_TOPDOWN_STRATEGY", True)
    monkeypatch.setattr(main_mod.config, "TOPDOWN_MIN_RR_RATIO", 1.5)
    await bot.trading_cycle()
