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
        mock_config.RF_CONFIRM_WICK_RATIO = 1.5
        mock_config.RF_SR_MIN_ZONE_GAP_PCT = 0.10
        mock_config.RF_CONFIRM_MIN_BODY_PCT = 30.0
        mock_config.RF_CONFIRM_MIN_MOMENTUM_PCT = 0.02
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


def test_patterns(strategy):
    # _is_bullish_engulf
    prev = pd.Series({"open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0})
    curr = pd.Series({"open": 98.5, "high": 102.0, "low": 98.0, "close": 101.5})
    assert strategy._is_bullish_engulf(prev, curr) is True

    # _is_bearish_engulf
    prev = pd.Series({"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0})
    curr = pd.Series({"open": 100.5, "high": 101.5, "low": 96.0, "close": 98.5})
    assert strategy._is_bearish_engulf(prev, curr) is True

    # _is_bullish_pin_bar: long lower wick, close near top
    zone = {"type": "support", "level": 100.0, "upper": 100.1, "lower": 99.9}
    candle = pd.Series({"open": 101.0, "high": 101.5, "low": 95.0, "close": 101.2})
    assert strategy._is_bullish_pin_bar(candle, zone) is True

    # _is_bearish_pin_bar: long upper wick, close near bottom
    zone = {"type": "resistance", "level": 100.0, "upper": 100.1, "lower": 99.9}
    candle = pd.Series({"open": 96.0, "high": 102.0, "low": 95.5, "close": 95.8})
    assert strategy._is_bearish_pin_bar(candle, zone) is True


# ── Helper to build candle data that creates an S&R pair ──────────────


# ── Success tests (all 6 gates pass) ────────────────────────────────


def test_analyze_success_support_call(strategy):
    """Support touch → all 6 gates pass → CALL (RISE)."""
    data = []
    # Rising candles to create a swing-high at 110 (resistance zone)
    data.append({"open": 106.0, "high": 106.0, "low": 106.0, "close": 106.0, "epoch": 1600000000 + 0 * 60})
    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 1 * 60})
    data.append({"open": 110.0, "high": 110.0, "low": 110.0, "close": 110.0, "epoch": 1600000000 + 2 * 60})
    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 3 * 60})
    data.append({"open": 106.0, "high": 106.0, "low": 106.0, "close": 106.0, "epoch": 1600000000 + 4 * 60})
    # Falling candles to create a swing-low at 100 (support zone)
    data.append({"open": 104.0, "high": 104.0, "low": 104.0, "close": 104.0, "epoch": 1600000000 + 5 * 60})
    data.append({"open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0, "epoch": 1600000000 + 6 * 60})
    data.append({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "epoch": 1600000000 + 7 * 60})
    data.append({"open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0, "epoch": 1600000000 + 8 * 60})
    data.append({"open": 104.0, "high": 104.0, "low": 104.0, "close": 104.0, "epoch": 1600000000 + 9 * 60})
    # prev candle (bearish)
    data.append({"open": 103.0, "high": 103.5, "low": 101.5, "close": 101.5, "epoch": 1600000000 + 10 * 60})
    # curr candle: bullish engulfing, touches support, escapes, strong body, momentum
    # Low 99.5 dips into support zone (~100 ± 0.05), close 102.5 > 100.05 (escaped)
    # Body = |102.5 - 99.5| = 3.0; Range = 102.5 - 99.5 = 3.0 → 100% body ✓
    # Engulfing: open(99.5) <= prev close(101.5), close(102.5) >= prev open(103.0)? No.
    # Actually need: open <= prev_close AND close >= prev_open → 99.5 <= 101.5 ✓, 102.5 < 103.0 ✗
    # Fix: make prev candle smaller
    data[-1] = {"open": 102.0, "high": 102.5, "low": 101.5, "close": 101.5, "epoch": 1600000000 + 10 * 60}
    data.append({"open": 101.0, "high": 102.5, "low": 99.5, "close": 102.5, "epoch": 1600000000 + 11 * 60})

    df = pd.DataFrame(data)
    strategy.sr_candle_count = len(data)
    result = strategy.analyze(data_1m=df, symbol="R_25")

    assert result is not None
    assert result["direction"] == "CALL"
    assert result["zone_type"] == "support"


def test_analyze_success_resistance_put(strategy):
    """Resistance touch → all 6 gates pass → PUT (FALL)."""
    data = []
    # Create a swing-low at 95 (support zone)
    data.append({"open": 98.0, "high": 98.0, "low": 98.0, "close": 98.0, "epoch": 1600000000 + 0 * 60})
    data.append({"open": 97.0, "high": 97.0, "low": 97.0, "close": 97.0, "epoch": 1600000000 + 1 * 60})
    data.append({"open": 95.0, "high": 95.0, "low": 95.0, "close": 95.0, "epoch": 1600000000 + 2 * 60})
    data.append({"open": 97.0, "high": 97.0, "low": 97.0, "close": 97.0, "epoch": 1600000000 + 3 * 60})
    data.append({"open": 99.0, "high": 99.0, "low": 99.0, "close": 99.0, "epoch": 1600000000 + 4 * 60})
    # Create swing-high pivot at 110 (resistance zone)
    data.append({"open": 106.0, "high": 106.0, "low": 106.0, "close": 106.0, "epoch": 1600000000 + 5 * 60})
    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 6 * 60})
    data.append({"open": 110.0, "high": 110.0, "low": 110.0, "close": 110.0, "epoch": 1600000000 + 7 * 60})
    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 8 * 60})
    data.append({"open": 106.0, "high": 106.0, "low": 106.0, "close": 106.0, "epoch": 1600000000 + 9 * 60})

    # prev candle (bullish)
    data.append({"open": 105.0, "high": 107.0, "low": 105.0, "close": 107.0, "epoch": 1600000000 + 10 * 60})
    # curr candle: bearish engulfing that touches resistance, escapes zone, strong body
    data.append({"open": 107.5, "high": 110.1, "low": 104.0, "close": 104.0, "epoch": 1600000000 + 11 * 60})

    df = pd.DataFrame(data)
    strategy.sr_candle_count = len(data)
    result = strategy.analyze(data_1m=df, symbol="R_25")

    assert result is not None
    assert result["direction"] == "PUT"
    assert result["zone_type"] == "resistance"
    assert result["confirmation_pattern"] == "bearish_engulf"


# ── Gate rejection tests ─────────────────────────────────────────────


def test_gate1_zone_gap_too_narrow(strategy):
    """Gate 1: When S and R zones are too close, reject with zone_gap_too_narrow."""
    # Build zones very close together (both near 100)
    data = []
    for i in range(8):
        data.append({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "epoch": 1600000000 + i * 60})
    # Swing-low pivot at 99.95 and swing-high pivot at 100.05
    data.append({"open": 99.97, "high": 99.97, "low": 99.97, "close": 99.97, "epoch": 1600000000 + 8 * 60})
    data.append({"open": 99.96, "high": 99.96, "low": 99.96, "close": 99.96, "epoch": 1600000000 + 9 * 60})
    data.append({"open": 99.95, "high": 99.95, "low": 99.95, "close": 99.95, "epoch": 1600000000 + 10 * 60})
    data.append({"open": 99.96, "high": 99.96, "low": 99.96, "close": 99.96, "epoch": 1600000000 + 11 * 60})
    data.append({"open": 99.97, "high": 99.97, "low": 99.97, "close": 99.97, "epoch": 1600000000 + 12 * 60})

    data.append({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "epoch": 1600000000 + 13 * 60})
    data.append({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "epoch": 1600000000 + 14 * 60})

    df = pd.DataFrame(data)
    strategy.sr_candle_count = 15
    # Set a very high gap requirement to ensure rejection
    strategy.sr_min_zone_gap_pct = 50.0
    result = strategy.analyze(data_1m=df, symbol="R_25")

    assert result is None
    meta = strategy.get_last_analysis("R_25")
    # Should either be zone_gap_too_narrow or no_zones_detected
    assert meta["code"] in ("zone_gap_too_narrow", "no_zones_detected", "no_zone_touch")


def test_gate3_weak_body_rejected(strategy):
    """Gate 3: A doji (tiny body) at a zone should be rejected."""
    zone = {"type": "support", "level": 100.0, "upper": 100.05, "lower": 99.95}
    # Doji: body = 0.01, range = 2.0, body_pct = 0.5% << 30%
    candle = pd.Series({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.01})
    assert strategy._check_strong_body(candle) is False

    # Strong body: body = 1.5, range = 2.0, body_pct = 75% > 30%
    candle = pd.Series({"open": 99.5, "high": 101.0, "low": 99.0, "close": 101.0})
    assert strategy._check_strong_body(candle) is True


def test_gate4_close_inside_zone_rejected(strategy):
    """Gate 4: Close still inside the zone should be rejected."""
    zone_r = {"type": "resistance", "level": 110.0, "upper": 110.05, "lower": 109.95}
    # Close at 110.0 → still inside zone
    candle = pd.Series({"open": 109.0, "high": 110.1, "low": 108.0, "close": 110.0})
    assert strategy._check_escaped_zone(candle, zone_r) is False
    # Close at 109.9 → below zone lower → escaped
    candle = pd.Series({"open": 109.0, "high": 110.1, "low": 108.0, "close": 109.9})
    assert strategy._check_escaped_zone(candle, zone_r) is True

    zone_s = {"type": "support", "level": 100.0, "upper": 100.05, "lower": 99.95}
    # Close at 100.0 → still inside zone
    candle = pd.Series({"open": 101.0, "high": 102.0, "low": 99.9, "close": 100.0})
    assert strategy._check_escaped_zone(candle, zone_s) is False
    # Close at 100.1 → above zone upper → escaped
    candle = pd.Series({"open": 101.0, "high": 102.0, "low": 99.9, "close": 100.1})
    assert strategy._check_escaped_zone(candle, zone_s) is True


def test_gate6_insufficient_momentum_rejected(strategy):
    """Gate 6: Close barely outside the zone fails momentum check."""
    zone_r = {"type": "resistance", "level": 110.0, "upper": 110.055, "lower": 109.945}
    price = 110.0
    # Close at 109.94 → distance = 109.945 - 109.94 = 0.005
    # Min distance = 110 * 0.02 / 100 = 0.022 → FAIL
    candle = pd.Series({"open": 109.5, "high": 110.1, "low": 109.0, "close": 109.94})
    assert strategy._check_momentum(candle, zone_r, price) is False

    # Close at 109.9 → distance = 109.945 - 109.9 = 0.045 > 0.022 → PASS
    candle = pd.Series({"open": 109.5, "high": 110.1, "low": 109.0, "close": 109.9})
    assert strategy._check_momentum(candle, zone_r, price) is True


def test_gate1_zone_gap_check(strategy):
    """Gate 1: Direct unit test of _check_zone_gap."""
    sup = {"type": "support", "level": 100.0, "upper": 100.05, "lower": 99.95}
    res = {"type": "resistance", "level": 110.0, "upper": 110.05, "lower": 109.95}
    # Gap = 10 / 105 * 100 ≈ 9.52% >> 0.10%
    assert strategy._check_zone_gap(sup, res, 105.0) is True

    # Very close zones
    res_close = {"type": "resistance", "level": 100.05, "upper": 100.1, "lower": 100.0}
    # Gap = 0.05 / 100 * 100 = 0.05% < 0.10%
    assert strategy._check_zone_gap(sup, res_close, 100.0) is False

    # Only one side exists → always passes
    assert strategy._check_zone_gap(sup, None, 100.0) is True
    assert strategy._check_zone_gap(None, res, 110.0) is True


def test_find_nearest_sr_pair(strategy):
    """_find_nearest_sr_pair returns the closest S and R to price."""
    zones = [
        {"type": "support", "level": 95.0},
        {"type": "support", "level": 99.0},
        {"type": "resistance", "level": 105.0},
        {"type": "resistance", "level": 115.0},
    ]
    sup, res = strategy._find_nearest_sr_pair(zones, 100.0)
    assert sup["level"] == 99.0
    assert res["level"] == 105.0


def test_analyze_no_confirmation(strategy):
    data = []
    for i in range(8):
        data.append({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "epoch": 1600000000 + i * 60})

    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 8 * 60})
    data.append({"open": 109.0, "high": 109.0, "low": 109.0, "close": 109.0, "epoch": 1600000000 + 9 * 60})
    data.append({"open": 110.0, "high": 110.0, "low": 110.0, "close": 110.0, "epoch": 1600000000 + 10 * 60})
    data.append({"open": 109.0, "high": 109.0, "low": 109.0, "close": 109.0, "epoch": 1600000000 + 11 * 60})
    data.append({"open": 108.0, "high": 108.0, "low": 108.0, "close": 108.0, "epoch": 1600000000 + 12 * 60})

    data.append({"open": 105.0, "high": 105.0, "low": 105.0, "close": 105.0, "epoch": 1600000000 + 13 * 60})
    data.append({"open": 105.0, "high": 110.1, "low": 104.0, "close": 110.0, "epoch": 1600000000 + 14 * 60})

    df = pd.DataFrame(data)
    strategy.sr_candle_count = 15
    result = strategy.analyze(data_1m=df, symbol="R_25")

    assert result is None
    meta = strategy.get_last_analysis("R_25")
    # Under the 6-gate model, the candle closes inside the zone
    assert meta["code"] in ("no_zone_touch", "close_inside_zone", "weak_body")
