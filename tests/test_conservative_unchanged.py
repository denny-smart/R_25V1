"""
Regression Test for Conservative Bot
Verifies that the new wrapper classes behave identically to the original logic.
"""

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import original classes
from strategy import TradingStrategy
from risk_manager import RiskManager

# Import wrapper classes
from conservative_strategy import ConservativeStrategy
from conservative_risk_manager import ConservativeRiskManager
from base_strategy import BaseStrategy
from base_risk_manager import BaseRiskManager
import config


class TestConservativeRegression(unittest.TestCase):
    
    def setUp(self):
        # Create dummy data
        self.data = pd.DataFrame({
            'timestamp': pd.date_range(start='2023-01-01', periods=100, freq='1min'),
            'open': np.random.randn(100) + 100,
            'high': np.random.randn(100) + 101,
            'low': np.random.randn(100) + 99,
            'close': np.random.randn(100) + 100,
            'volume': np.random.randn(100) * 1000
        })
        
        self.kwargs = {
            'data_1m': self.data,
            'data_5m': self.data,
            'data_1h': self.data,
            'data_4h': self.data,
            'data_1d': self.data,
            'data_1w': self.data,
            'symbol': 'R_50'
        }

    def test_strategy_wrapper_delegation(self):
        """Test that wrapper delegates correctly to original strategy"""
        
        # Instantiate both
        original = TradingStrategy()
        wrapper = ConservativeStrategy()
        
        # Mock the analyze method on the internal strategy instance
        with patch.object(wrapper.strategy, 'analyze', return_value={'signal': 'UP'}) as mock_analyze:
            result = wrapper.analyze(**self.kwargs)
            
            # Verify delegation
            self.assertEqual(result, {'signal': 'UP'})
            mock_analyze.assert_called_once()
            
            # Verify arguments passed correctly
            call_args = mock_analyze.call_args[1]
            self.assertEqual(call_args['symbol'], 'R_50')
            self.assertIs(call_args['data_1m'], self.data)
    
    def test_risk_manager_wrapper_delegation(self):
        """Test that risk manager wrapper delegates correctly"""
        
        original = RiskManager()
        wrapper = ConservativeRiskManager(user_id="test_user")
        
        # 1. Test can_trade delegation
        with patch.object(wrapper.risk_manager, 'can_trade', return_value=(True, "OK")) as mock_can_trade:
            can_trade, reason = wrapper.can_trade()
            self.assertTrue(can_trade)
            self.assertEqual(reason, "OK")
            mock_can_trade.assert_called_once()
            
        # 2. Test record_trade_open delegation
        with patch.object(wrapper.risk_manager, 'record_trade_open') as mock_record_open:
            trade_info = {'contract_id': '123'}
            wrapper.record_trade_opened(trade_info)
            mock_record_open.assert_called_once_with(trade_info)
            
        # 3. Test record_trade_close delegation
        with patch.object(wrapper.risk_manager, 'record_trade_close') as mock_record_close:
            result = {'contract_id': '123', 'profit': 10.0, 'status': 'win'}
            wrapper.record_trade_closed(result)
            mock_record_close.assert_called_once_with(contract_id='123', pnl=10.0, status='win')
            
    def test_interface_compliance(self):
        """Verify wrappers implement abstract base classes"""
        self.assertTrue(issubclass(ConservativeStrategy, BaseStrategy))
        self.assertTrue(issubclass(ConservativeRiskManager, BaseRiskManager))
        
        strat = ConservativeStrategy()
        self.assertEqual(strat.get_strategy_name(), "Conservative")
        self.assertEqual(strat.get_required_timeframes(), ['1w', '1d', '4h', '1h', '5m', '1m'])

    def test_risk_limits_match_config(self):
        """Verify get_current_limits returns correct config values"""
        wrapper = ConservativeRiskManager(user_id="test")
        limits = wrapper.get_current_limits()
        
        self.assertEqual(limits['max_concurrent_trades'], config.MAX_CONCURRENT_TRADES)
        self.assertEqual(limits['max_trades_per_day'], config.MAX_TRADES_PER_DAY)
        self.assertEqual(limits['cooldown_seconds'], config.COOLDOWN_SECONDS)

if __name__ == '__main__':
    unittest.main()

