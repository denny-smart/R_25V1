import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from main import TradingBot

@pytest.fixture
def bot():
    with patch("main.setup_logger"):
        return TradingBot()

@pytest.mark.asyncio
async def test_bot_initialize_success(bot):
    """Test successful bot initialization."""
    with patch("main.config") as mock_config, \
         patch("main.DataFetcher") as mock_df_class, \
         patch("main.TradeEngine") as mock_te_class, \
         patch("main.TradingStrategy") as mock_strat_class, \
         patch("main.RiskManager") as mock_rm_class:
        
        mock_config.DERIV_API_TOKEN = "fake_token"
        mock_config.DERIV_APP_ID = "1234"
        mock_config.get_all_symbols.return_value = ["R_25"]
        mock_config.FIXED_STAKE = 10.0
        mock_config.USE_TOPDOWN_STRATEGY = True
        mock_config.MAX_CONCURRENT_TRADES = 2
        mock_config.TOPDOWN_MIN_RR_RATIO = 1.5
        mock_config.COOLDOWN_SECONDS = 60
        mock_config.MAX_TRADES_PER_DAY = 10
        mock_config.MAX_DAILY_LOSS = 50.0
        mock_config.LOG_FILE = "test.log"
        mock_config.LOG_LEVEL = "INFO"
        
        mock_df = mock_df_class.return_value
        mock_df.connect = AsyncMock(return_value=True)
        mock_df.get_balance = AsyncMock(return_value=1000.0)
        
        mock_te = mock_te_class.return_value
        mock_te.connect = AsyncMock(return_value=True)
        mock_te.authorize = AsyncMock(return_value=True) # Ensure authorize is mocked if called
        
        success = await bot.initialize()
        if not success:
            print("Initialization failed")
        
        assert success is True
        assert bot.data_fetcher is not None
        assert bot.trade_engine is not None
        assert bot.strategy is not None
        assert bot.risk_manager is not None

@pytest.mark.asyncio
async def test_bot_initialize_failure(bot):
    """Test bot initialization failure (connection error)."""
    with patch("main.config"), \
         patch("main.DataFetcher") as mock_df_class, \
         patch("main.TradeEngine") as mock_te_class, \
         patch("main.TradingStrategy"), \
         patch("main.RiskManager"):
        
        mock_df = mock_df_class.return_value
        mock_df.connect = AsyncMock(return_value=False)
        
        success = await bot.initialize()
        assert success is False

@pytest.mark.asyncio
async def test_bot_shutdown(bot):
    """Test bot shutdown sequence."""
    bot.data_fetcher = AsyncMock()
    bot.trade_engine = AsyncMock()
    bot.risk_manager = MagicMock()
    bot.risk_manager.get_statistics.return_value = {"total_pnl": 0}
    
    await bot.shutdown()
    
    bot.data_fetcher.disconnect.assert_called_once()
    bot.trade_engine.disconnect.assert_called_once()
    bot.risk_manager.get_statistics.assert_called_once()

@pytest.mark.asyncio
async def test_analyze_asset_topdown(bot):
    """Test asset analysis in Top-Down mode."""
    bot.data_fetcher = AsyncMock()
    bot.strategy = MagicMock()
    
    with patch("main.config") as mock_config:
        mock_config.USE_TOPDOWN_STRATEGY = True
        mock_config.get_asset_info.return_value = {"multiplier": 100}
        
        bot.data_fetcher.fetch_all_timeframes.return_value = {"1m": MagicMock(), "1d": MagicMock()}
        bot.strategy.analyze.return_value = {"signal": "UP", "can_trade": True}
        
        signal = await bot.analyze_asset("R_25")
        
        assert signal["symbol"] == "R_25"
        assert signal["signal"] == "UP"
        bot.strategy.analyze.assert_called_once()

@pytest.mark.asyncio
async def test_scan_all_assets(bot):
    """Test scanning multiple assets in parallel."""
    bot.symbols = ["R_25", "R_50"]
    bot.analyze_asset = AsyncMock()
    bot.analyze_asset.side_effect = [
        {"symbol": "R_25", "signal": "UP", "can_trade": True, "score": 10, "details": {}},
        {"symbol": "R_50", "signal": "DOWN", "can_trade": True, "score": 20, "details": {}}
    ]
    
    with patch("main.config") as mock_config:
        mock_config.PRIORITIZE_BY_SIGNAL_STRENGTH = True
        
        signals = await bot.scan_all_assets()
        
        assert len(signals) == 2
        # Highest score first
        assert signals[0]["symbol"] == "R_50"
        assert signals[1]["symbol"] == "R_25"

@pytest.mark.asyncio
async def test_trading_cycle_no_trade(bot):
    """Test trading cycle when no signals are found."""
    bot.risk_manager = MagicMock()
    bot.risk_manager.can_trade.return_value = (True, "OK")
    bot.scan_all_assets = AsyncMock(return_value=[])
    
    await bot.trading_cycle()
    # No further calls expected

@pytest.mark.asyncio
async def test_trading_cycle_execute(bot):
    """Test trading cycle leading to trade execution."""
    bot.risk_manager = MagicMock()
    bot.risk_manager.can_trade.return_value = (True, "OK")
    bot.risk_manager.validate_trade_parameters.return_value = (True, "OK")
    
    bot.scan_all_assets = AsyncMock(return_value=[{
        "symbol": "R_25", "signal": "UP", "can_trade": True, "score": 10,
        "take_profit": 105.0, "stop_loss": 95.0, "entry_price": 100.0, "risk_reward_ratio": 2.0
    }])
    
    bot.trade_engine = AsyncMock()
    bot.trade_engine.execute_trade.return_value = {
        "contract_id": "c123", "profit": 5.0, "status": "won"
    }
    
    with patch("main.config") as mock_config:
        mock_config.USE_TOPDOWN_STRATEGY = True
        mock_config.TOPDOWN_MIN_RR_RATIO = 1.5
        
        await bot.trading_cycle()
        
        bot.trade_engine.execute_trade.assert_called_once()
        bot.risk_manager.record_trade_close.assert_called_once_with("c123", 5.0, "won")

@pytest.mark.asyncio
async def test_run_loop_interrupted(bot):
    """Test main run loop with immediate interruption."""
    bot.initialize = AsyncMock(return_value=True)
    bot.shutdown = AsyncMock()
    bot.trading_cycle = AsyncMock()
    
    # Mock running to false immediately to exit while loop
    bot.running = True
    
    def side_effect():
        bot.running = False
    
    bot.trading_cycle.side_effect = side_effect
    
    with patch("main.asyncio.sleep", return_value=None):
        await bot.run()
        
    bot.initialize.assert_called_once()
    bot.trading_cycle.assert_called_once()
    bot.shutdown.assert_called_once()
