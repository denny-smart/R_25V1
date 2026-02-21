import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from scalping_strategy import ScalpingStrategy

@pytest.fixture
def strategy():
    return ScalpingStrategy()

@pytest.fixture
def mock_ohlc():
    """Create basic 60-candle FLAT OHLC data for stable testing."""
    dates = pd.date_range('2024-01-01', periods=60, freq='1min')
    df = pd.DataFrame({
        'open': [100.0] * 60,
        'high': [101.0] * 60,
        'low': [99.0] * 60,
        'close': [100.0] * 60
    }, index=dates)
    return df

class TestScalpingStrategyInit:
    def test_init_success(self, strategy):
        assert strategy.get_strategy_name() == "Scalping"
        assert "1h" in strategy.get_required_timeframes()
        assert "5m" in strategy.get_required_timeframes()
        assert "1m" in strategy.get_required_timeframes()

class TestScalpingStrategyTrend:
    def test_determine_trend_up(self, strategy):
        df = pd.DataFrame({'close': [100.0] * 30})
        with patch.object(ScalpingStrategy, '_calculate_ema') as mock_ema:
            mock_ema.side_effect = [
                pd.Series([110.0] * 30), # fast
                pd.Series([100.0] * 30)  # slow
            ]
            trend = strategy._determine_trend(df, "1h")
            assert trend == "UP"

    def test_determine_trend_down(self, strategy):
        df = pd.DataFrame({'close': [100.0] * 30})
        with patch.object(ScalpingStrategy, '_calculate_ema') as mock_ema:
            mock_ema.side_effect = [
                pd.Series([90.0] * 30),  # fast
                pd.Series([100.0] * 30)  # slow
            ]
            trend = strategy._determine_trend(df, "1h")
            assert trend == "DOWN"

class TestScalpingStrategyAnalyze:
    def test_analyze_missing_data(self, strategy):
        result = strategy.analyze(data_1h=None, data_5m=pd.DataFrame(), data_1m=pd.DataFrame())
        assert result['can_trade'] is False
        assert "Missing" in result['details']['reason']

    def test_analyze_insufficient_data_length(self, strategy):
        short_df = pd.DataFrame({'close': [100] * 10})
        result = strategy.analyze(data_1h=short_df, data_5m=short_df, data_1m=short_df)
        assert result['can_trade'] is False
        assert "Insufficient data" in result['details']['reason']

    @patch('scalping_strategy.calculate_rsi')
    @patch('scalping_strategy.calculate_adx')
    def test_analyze_trend_mismatch(self, mock_adx, mock_rsi, strategy, mock_ohlc):
        with patch.object(ScalpingStrategy, '_determine_trend') as mock_trend:
            mock_trend.side_effect = ["UP", "DOWN"]
            result = strategy.analyze(data_1h=mock_ohlc, data_5m=mock_ohlc, data_1m=mock_ohlc)
            assert result['can_trade'] is False
            assert "Trend mismatch" in result['details']['reason']

    @patch('scalping_strategy.calculate_rsi')
    @patch('scalping_strategy.calculate_adx')
    def test_analyze_weak_adx(self, mock_adx, mock_rsi, strategy, mock_ohlc):
        with patch.object(ScalpingStrategy, '_determine_trend', return_value="UP"):
            mock_adx.return_value = pd.Series([10.0] * 60)
            mock_rsi.return_value = pd.Series([60.0] * 60)
            result = strategy.analyze(data_1h=mock_ohlc, data_5m=mock_ohlc, data_1m=mock_ohlc)
            assert result['can_trade'] is False
            assert "Weak trend" in result['details']['reason']

    @patch('scalping_strategy.calculate_rsi')
    @patch('scalping_strategy.calculate_adx')
    def test_analyze_rsi_out_of_range_up(self, mock_adx, mock_rsi, strategy, mock_ohlc):
        with patch.object(ScalpingStrategy, '_determine_trend', return_value="UP"):
            mock_adx.return_value = pd.Series([25.0] * 60)
            mock_rsi.return_value = pd.Series([40.0] * 60)
            result = strategy.analyze(data_1h=mock_ohlc, data_5m=mock_ohlc, data_1m=mock_ohlc)
            assert result['can_trade'] is False
            assert "RSI" in result['details']['reason']

    @patch('scalping_strategy.calculate_rsi')
    @patch('scalping_strategy.calculate_adx')
    def test_analyze_no_momentum_breakout(self, mock_adx, mock_rsi, strategy, mock_ohlc):
        with patch.object(ScalpingStrategy, '_determine_trend', return_value="UP"), \
             patch.object(ScalpingStrategy, '_calculate_atr', return_value=10.0):
            mock_adx.return_value = pd.Series([25.0] * 60)
            mock_rsi.return_value = pd.Series([60.0] * 60)
            
            # Last candle is tiny (0.1) vs momentum threshold (10.0 * 1.2 = 12.0)
            mock_ohlc.iloc[-1, mock_ohlc.columns.get_loc('open')] = 100.0
            mock_ohlc.iloc[-1, mock_ohlc.columns.get_loc('close')] = 100.1
            
            result = strategy.analyze(data_1h=mock_ohlc, data_5m=mock_ohlc, data_1m=mock_ohlc)
            assert result['can_trade'] is False
            assert "momentum" in result['details']['reason'].lower()

class TestScalpingStrategyEdgeCases:
    def test_is_parabolic_spike_true(self, strategy, mock_ohlc):
        atr = 1.0
        mock_ohlc.iloc[-3:, mock_ohlc.columns.get_loc('open')] = 100.0
        mock_ohlc.iloc[-3:, mock_ohlc.columns.get_loc('close')] = 103.0 
        assert strategy._is_parabolic_spike(mock_ohlc, atr) is True

    def test_calculate_atr_basic(self, strategy, mock_ohlc):
        atr = strategy._calculate_atr(mock_ohlc, period=14)
        assert atr > 0

    @patch('scalping_strategy.calculate_rsi')
    @patch('scalping_strategy.calculate_adx')
    def test_analyze_parabolic_spike_fails(self, mock_adx, mock_rsi, strategy, mock_ohlc):
         with patch.object(ScalpingStrategy, '_determine_trend', return_value="UP"), \
              patch.object(ScalpingStrategy, '_calculate_atr', return_value=0.5), \
              patch.object(ScalpingStrategy, '_is_parabolic_spike', return_value=True):
            mock_adx.return_value = pd.Series([25.0] * 60)
            mock_rsi.return_value = pd.Series([60.0] * 60)

            # ATR = 0.5, Momentum threshold = 0.5 * 1.2 = 0.6
            # Price Movement threshold = ~1.19%
            # Size 0.8 is > 0.6 (Passes Check 6) and < 1.19% (Passes Check 5)
            mock_ohlc.iloc[-1, mock_ohlc.columns.get_loc('open')] = 100.0
            mock_ohlc.iloc[-1, mock_ohlc.columns.get_loc('close')] = 100.8
             
            result = strategy.analyze(data_1h=mock_ohlc, data_5m=mock_ohlc, data_1m=mock_ohlc)
            assert result['can_trade'] is False
            assert "Parabolic" in result['details']['reason']

    @patch('scalping_strategy.calculate_rsi')
    @patch('scalping_strategy.calculate_adx')
    def test_analyze_success_up(self, mock_adx, mock_rsi, strategy, mock_ohlc):
        with patch.object(ScalpingStrategy, '_determine_trend', return_value="UP"), \
             patch.object(ScalpingStrategy, '_calculate_atr', return_value=0.5), \
             patch.object(ScalpingStrategy, '_is_parabolic_spike', return_value=False):
            
            mock_adx.return_value = pd.Series([25.0] * 60)
            mock_rsi.return_value = pd.Series([60.0] * 60)
            
            # Size 0.8 passes both Check 5 (Movement) and Check 6 (Momentum)
            mock_ohlc.iloc[-1, mock_ohlc.columns.get_loc('open')] = 100.0
            mock_ohlc.iloc[-1, mock_ohlc.columns.get_loc('close')] = 100.8
            
            result = strategy.analyze(data_1h=mock_ohlc, data_5m=mock_ohlc, data_1m=mock_ohlc)
            assert result['can_trade'] is True
            assert result['signal'] == "UP"
            assert 'take_profit' in result
            assert 'stop_loss' in result
