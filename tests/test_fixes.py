import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
import pandas as pd
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# MOCK MISSING DEPENDENCIES BEFORE IMPORTS
class MockModule(MagicMock):
    pass

sys.modules['fastapi'] = MockModule()
sys.modules['uvicorn'] = MockModule()
sys.modules['telegram'] = MockModule()
sys.modules['telegram.ext'] = MockModule()

# Now import bot modules
from app.bot.runner import BotRunner
from trade_engine import TradeEngine
from strategy import TradingStrategy
from data_fetcher import DataFetcher
from risk_manager import RiskManager

# Configure logging to swallow output during tests
logging.basicConfig(level=logging.CRITICAL)

class TestBugFixes(unittest.TestCase):
    def setUp(self):
        # Setup mocks
        self.runner = BotRunner()
        self.runner.data_fetcher = AsyncMock(spec=DataFetcher)
        self.runner.strategy = MagicMock(spec=TradingStrategy)
        self.runner.risk_manager = MagicMock(spec=RiskManager)
        self.runner.trade_engine = AsyncMock(spec=TradeEngine)
        
        # Mock strategy analyze return
        self.runner.strategy.analyze.return_value = {
            'can_trade': True,
            'signal': 'UP', 
            'score': 10, 
            'confidence': 90
        }
        
        # Mock risk manager
        self.runner.risk_manager.can_trade.return_value = (True, "OK")
        self.runner.risk_manager.can_open_trade.return_value = (True, "OK")

    def test_runner_calls_fetch_all_timeframes(self):
        """Verify runner calls fetch_all_timeframes and passes 1w data"""
        async def run_test():
            # Mock data return
            mock_data = {
                '1m': pd.DataFrame({'close': [1]}),
                '5m': pd.DataFrame({'close': [1]}),
                '1h': pd.DataFrame({'close': [1]}),
                '4h': pd.DataFrame({'close': [1]}),
                '1d': pd.DataFrame({'close': [1]}),
                '1w': pd.DataFrame({'close': [1]})
            }
            self.runner.data_fetcher.fetch_all_timeframes.return_value = mock_data
            
            # Use 'R_25' as test symbol (from config or just logic)
            symbol = "R_25"
            await self.runner._analyze_symbol(symbol)
            
            # Check if fetch_all_timeframes was called
            self.runner.data_fetcher.fetch_all_timeframes.assert_called_with(symbol)
            
            # Check if strategy.analyze was called with 6 args
            # analyze(data_1m, data_5m, data_1h, data_4h, data_1d, data_1w)
            args, _ = self.runner.strategy.analyze.call_args
            self.assertEqual(len(args), 6)
            self.assertTrue(all(isinstance(arg, pd.DataFrame) for arg in args))

        asyncio.run(run_test())

    def test_runner_handles_fetch_error(self):
        """Verify runner handles data fetch error gracefully"""
        async def run_test():
            # Mock fetch error
            self.runner.data_fetcher.fetch_all_timeframes.side_effect = Exception("Fetch failed")
            
            # Just verify it raises Exception (as it re-raises in the code)
            # The calling loop in _multi_asset_scan_cycle catches it.
            with self.assertRaises(Exception):
                await self.runner._analyze_symbol("R_25")

        asyncio.run(run_test())

    def test_trade_engine_portfolio_method(self):
        """Verify TradeEngine has portfolio method"""
        engine = TradeEngine("token")
        engine.send_request = AsyncMock(return_value={"portfolio": {}})
        
        async def run_test():
            await engine.portfolio({"portfolio": 1})
            engine.send_request.assert_called_with({"portfolio": 1})

        asyncio.run(run_test())

    def test_risk_manager_async_check(self):
        """Verify RiskManager check_for_existing_positions is async and works"""
        rm = RiskManager()
        
        # Mock deriv_api
        mock_api = MagicMock()
        mock_api.portfolio = AsyncMock(return_value={'portfolio': {'contracts': []}})
        
        async def run_test():
            result = await rm.check_for_existing_positions(mock_api)
            self.assertFalse(result)
            mock_api.portfolio.assert_called_once()
            
        asyncio.run(run_test())

    def test_data_fetcher_resampling(self):
        """Verify DataFetcher resamples 1d to 1w"""
        fetcher = DataFetcher("token")
        
        # Create dummy 1d data
        dates = pd.date_range(start='2024-01-01', periods=14, freq='D')
        df_daily = pd.DataFrame({
            'datetime': dates,
            'open': [100]*14,
            'high': [110]*14,
            'low': [90]*14,
            'close': [105]*14,
            'timestamp': [d.timestamp() for d in dates]
        })
        
        # Test private method directly
        df_weekly = fetcher._resample_to_weekly(df_daily)
        
        self.assertIsNotNone(df_weekly)
        # Should be roughly 2 weeks
        self.assertTrue(len(df_weekly) >= 2)
        # Check columns
        self.assertIn('open', df_weekly.columns)
        self.assertIn('datetime', df_weekly.columns)

        async def run_fetch_test():
            # Mock fetch_candles to return df_daily
            fetcher.fetch_candles = AsyncMock(return_value=df_daily)
            
            # Request 1w data
            df_result = await fetcher.fetch_timeframe("R_25", "1w", count=2)
            
            self.assertIsNotNone(df_result)
            # fetch_candles called with 1d granularity (86400) and 7x count
            fetcher.fetch_candles.assert_called_with("R_25", 86400, 14)
            
        asyncio.run(run_fetch_test())

if __name__ == '__main__':
    unittest.main()
