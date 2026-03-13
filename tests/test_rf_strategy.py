import pandas as pd
import pytest
from unittest.mock import patch

from risefallbot.rf_strategy import RiseFallStrategy


@pytest.fixture
def strategy():
    with patch("risefallbot.rf_strategy.rf_config") as mock_config:
        mock_config.RF_SYMBOLS = ["R_100S", "R_200S"]
        mock_config.RF_TICK_SEQUENCE_LENGTH = 4
        mock_config.RF_CONFIRMATION_TICKS = 2
        mock_config.RF_BURST_NOISE_LOOKBACK_MOVES = 4
        mock_config.RF_BURST_MAX_SECONDS = 0
        mock_config.RF_TICK_HISTORY_COUNT = 11
        mock_config.RF_REQUIRE_CONSECUTIVE_DIRECTION = True
        mock_config.RF_REQUIRE_FRESH_SIGNAL_AFTER_COOLDOWN = True
        mock_config.RF_DEFAULT_STAKE = 10.0
        mock_config.RF_CONTRACT_DURATION = 5
        mock_config.RF_DURATION_UNIT = "t"
        yield RiseFallStrategy()


def _ticks(prices, step_seconds=1.0, start_epoch=1700000000.0):
    timestamps = [start_epoch + (idx * step_seconds) for idx in range(len(prices))]
    datetimes = pd.Timestamp("2026-01-01") + pd.to_timedelta(
        [idx * step_seconds for idx in range(len(prices))],
        unit="s",
    )
    return pd.DataFrame(
        {
            "quote": prices,
            "timestamp": timestamps,
            "datetime": datetimes,
        }
    )


def test_analyze_insufficient_tick_history(strategy):
    assert strategy.analyze(
        data_ticks=_ticks([100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.4]),
        symbol="R_100S",
    ) is None
    meta = strategy.get_last_analysis("R_100S")
    assert meta["code"] == "insufficient_tick_history"


def test_analyze_empty_data(strategy):
    assert strategy.analyze(data_ticks=None, symbol="R_100S") is None
    assert strategy.analyze(data_ticks=pd.DataFrame(), symbol="R_100S") is None


def test_analyze_strict_upward_burst_generates_fall(strategy):
    result = strategy.analyze(
        data_ticks=_ticks([100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.4]),
        symbol="R_100S",
    )

    assert result is not None
    assert result["direction"] == "PUT"
    assert result["trade_label"] == "FALL"
    assert result["sequence_direction"] == "up"
    assert result["burst_movements"] == [0.1, 0.1, 0.1, 0.1]
    assert result["confirmation_movements"] == [0.1, -0.1]
    assert result["pre_burst_movements"] == [0.1, -0.1, 0.1, -0.1]
    assert result["stake"] == 10.0
    assert result["duration"] == 5
    assert result["duration_unit"] == "t"


def test_analyze_strict_downward_burst_generates_rise(strategy):
    result = strategy.analyze(
        data_ticks=_ticks([100.5, 100.4, 100.5, 100.4, 100.5, 100.4, 100.3, 100.2, 100.1, 100.0, 100.1]),
        symbol="R_200S",
    )

    assert result is not None
    assert result["direction"] == "CALL"
    assert result["trade_label"] == "RISE"
    assert result["sequence_direction"] == "down"
    assert result["confirmation_movements"] == [-0.1, 0.1]


def test_burst_must_be_strictly_consecutive(strategy):
    assert strategy.analyze(
        data_ticks=_ticks([99.8, 99.9, 99.8, 99.9, 100.0, 100.1, 100.3, 100.2, 100.4, 100.5, 100.4]),
        symbol="R_100S",
    ) is None
    assert strategy.get_last_analysis("R_100S")["code"] == "burst_not_consecutive"

    assert strategy.analyze(
        data_ticks=_ticks([99.8, 99.9, 99.8, 99.9, 100.0, 100.1, 100.2, 100.2, 100.3, 100.4, 100.3]),
        symbol="R_100S",
    ) is None
    assert strategy.get_last_analysis("R_100S")["code"] == "burst_not_consecutive"


def test_confirmation_requires_full_opposite_tick(strategy):
    assert strategy.analyze(
        data_ticks=_ticks([100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.45, 100.4]),
        symbol="R_100S",
    ) is None
    assert strategy.get_last_analysis("R_100S")["code"] == "confirmation_no_genuine_reversal"

    assert strategy.analyze(
        data_ticks=_ticks([100.5, 100.4, 100.5, 100.4, 100.5, 100.4, 100.3, 100.2, 100.1, 100.05, 100.1]),
        symbol="R_200S",
    ) is None
    assert strategy.get_last_analysis("R_200S")["code"] == "confirmation_no_genuine_reversal"


def test_burst_speed_filter_is_disabled_for_fixed_cadence_step_index(strategy):
    result = strategy.analyze(
        data_ticks=_ticks(
            [100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.4],
            step_seconds=2.0,
        ),
        symbol="R_100S",
    )
    assert result is not None


def test_reuses_of_same_sequence_are_rejected_as_not_fresh(strategy):
    ticks = _ticks([100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.4])
    first = strategy.analyze(data_ticks=ticks, symbol="R_100S")
    second = strategy.analyze(data_ticks=ticks, symbol="R_100S")

    assert first is not None
    assert second is None
    assert strategy.get_last_analysis("R_100S")["code"] == "signal_not_fresh"


def test_same_direction_run_cooldown_blocks_stacked_signal(strategy):
    first = strategy.analyze(
        data_ticks=_ticks([100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.4]),
        symbol="R_100S",
    )
    assert first is not None

    second = strategy.analyze(
        data_ticks=_ticks(
            [
                100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.4,
                100.5, 100.6, 100.7, 100.8, 100.9, 100.8,
            ]
        ),
        symbol="R_100S",
    )

    assert second is None
    assert strategy.get_last_analysis("R_100S")["code"] == "directional_run_cooldown_active"


def test_same_direction_run_cooldown_clears_after_break_ticks(strategy):
    first = strategy.analyze(
        data_ticks=_ticks([100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.4]),
        symbol="R_100S",
    )
    assert first is not None

    second = strategy.analyze(
        data_ticks=_ticks(
            [
                100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.4,
                100.3, 100.2, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.4,
            ]
        ),
        symbol="R_100S",
    )

    assert second is not None
    assert second["direction"] == "PUT"


def test_symbol_not_allowed_rejected(strategy):
    assert strategy.analyze(
        data_ticks=_ticks([100.0, 100.1, 100.0, 100.1, 100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.4]),
        symbol="R_25",
    ) is None
    assert strategy.get_last_analysis("R_25")["code"] == "symbol_not_allowed"


def test_metadata(strategy):
    assert strategy.get_strategy_name() == "RiseFall"
    assert strategy.get_required_timeframes() == ["ticks"]
