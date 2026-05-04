import pandas as pd
import pytest
from unittest.mock import patch

from risefallbot.rf_strategy import RiseFallStrategy


@pytest.fixture
def strategy():
    with patch("risefallbot.rf_strategy.rf_config") as mock_config:
        mock_config.RF_SYMBOLS = ["R_25"]
        mock_config.RF_SR_CANDLE_COUNT = 10
        mock_config.RF_SR_PIVOT_WINDOW = 2
        mock_config.RF_SR_MIN_TOUCHES = 1
        yield RiseFallStrategy()


def test_metadata(strategy):
    assert strategy.get_strategy_name() == "RiseFall"
    assert strategy.get_required_timeframes() == ["1m"]


def test_analyze_insufficient_candle_history(strategy):
    # Pass fewer than RF_SR_CANDLE_COUNT candles
    df = pd.DataFrame({
        "open": [100.0] * 5,
        "high": [101.0] * 5,
        "low": [99.0] * 5,
        "close": [100.0] * 5,
        "timestamp": [1600000000 + i * 60 for i in range(5)]
    })
    assert strategy.analyze(data_1m=df, symbol="R_25") is None
    meta = strategy.get_last_analysis("R_25")
    assert meta["code"] == "insufficient_candle_history"


def test_analyze_empty_data(strategy):
    assert strategy.analyze(data_1m=None, symbol="R_25") is None
    assert strategy.analyze(data_1m=pd.DataFrame(), symbol="R_25") is None


def test_symbol_not_allowed_rejected(strategy):
    df = pd.DataFrame({
        "open": [100.0] * 12,
        "high": [101.0] * 12,
        "low": [99.0] * 12,
        "close": [100.0] * 12,
        "timestamp": [1600000000 + i * 60 for i in range(12)]
    })
    assert strategy.analyze(data_1m=df, symbol="R_100") is None
    meta = strategy.get_last_analysis("R_100")
    assert meta["code"] == "symbol_not_allowed"


def test_no_zones_detected(strategy):
    # A straight upward line will have no valid pivot highs/lows inside the window
    df = pd.DataFrame({
        "open": [100.0 + i for i in range(15)],
        "high": [100.0 + i for i in range(15)],
        "low": [100.0 + i for i in range(15)],
        "close": [100.0 + i for i in range(15)],
        "timestamp": [1600000000 + i * 60 for i in range(15)]
    })
    assert strategy.analyze(data_1m=df, symbol="R_25") is None
    meta = strategy.get_last_analysis("R_25")
    assert meta["code"] == "no_zones_detected"


def test_normalize_candles(strategy):
    raw = [{"open": 1, "high": 2, "low": 0, "close": 1, "epoch": 1600000000}]
    df = strategy._normalize_candles(raw)
    assert not df.empty
    assert "timestamp" in df.columns
    assert "datetime" in df.columns
    assert df["open"].iloc[0] == 1.0
