import asyncio
import logging
import sys

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock Config
import app.core.settings
from app.core.settings import Settings

# Ensure paths correct
sys.path.append(".")

# Mock config values to avoid connection errors during test
import config
config.DERIV_API_TOKEN = "DEFAULT_TOKEN"

# Mock External Dependencies
from unittest.mock import MagicMock, AsyncMock
import app.bot.runner

# Mock DataFetcher
mock_fetcher = MagicMock()
mock_fetcher.connect = AsyncMock(return_value=True) # Must be async
mock_fetcher.get_balance = AsyncMock(return_value=1000.0)
mock_fetcher.disconnect = AsyncMock()

# Mock TradeEngine
mock_engine = MagicMock()
mock_engine.connect = AsyncMock(return_value=True)
mock_engine.disconnect = AsyncMock()

# Mock RiskManager
mock_risk = MagicMock()
mock_risk.check_for_existing_positions = AsyncMock(return_value=False)

# Apply patches
app.bot.runner.DataFetcher = MagicMock(return_value=mock_fetcher)
app.bot.runner.TradeEngine = MagicMock(return_value=mock_engine)
app.bot.runner.RiskManager = MagicMock(return_value=mock_risk)

# Import Bot Manager
from app.bot.manager import BotManager, bot_manager

async def test_multi_user_isolation():
    logger.info("🧪 Testing Multi-User Bot Isolation...")
    
    user_a = "user_a_123"
    token_a = "TOKEN_A_XXXX"
    
    user_b = "user_b_456"
    token_b = "TOKEN_B_YYYY"
    
    # 1. Start Bot A
    logger.info(f"--- Starting Bot A (User: {user_a}) ---")
    await bot_manager.start_bot(user_a, api_token=token_a)
    bot_a = bot_manager.get_bot(user_a)
    
    if bot_a.api_token == token_a:
        logger.info("✅ Bot A initialized with correct token")
    else:
        logger.error(f"❌ Bot A token mismatch: {bot_a.api_token}")
        
    # 2. Start Bot B
    logger.info(f"--- Starting Bot B (User: {user_b}) ---")
    await bot_manager.start_bot(user_b, api_token=token_b)
    bot_b = bot_manager.get_bot(user_b)
    
    if bot_b.api_token == token_b:
        logger.info("✅ Bot B initialized with correct token")
    else:
        logger.error(f"❌ Bot B token mismatch: {bot_b.api_token}")
        
    # 3. Verify Isolation
    if bot_a is not bot_b:
        logger.info("✅ Bot instances are distinct")
    else:
        logger.error("❌ Bot instances are the SAME object!")
        
    if bot_a.state is not bot_b.state:
        logger.info("✅ Bot states are isolated")
    else:
        logger.error("❌ Bot states are SHARED!")

    # 4. Verify Default (Backwards Compat)
    logger.info("--- Testing Default/Global Bot ---")
    # If using pure BotManager, there is no "default" unless we manage it.
    # But the global `bot_runner` in runner.py should still exist.
    from app.bot.runner import bot_runner
    if bot_runner.api_token == config.DERIV_API_TOKEN:
         logger.info("✅ Global bot_runner uses default config token")
    
    logger.info("🎉 Verification Complete!")

if __name__ == "__main__":
    try:
        asyncio.run(test_multi_user_isolation())
    except Exception as e:
        logger.error(f"Test failed: {e}")
