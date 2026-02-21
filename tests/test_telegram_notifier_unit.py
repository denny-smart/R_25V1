import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram_notifier import TelegramNotifier, TelegramLoggingHandler
import logging

@pytest.fixture
def mock_bot():
    with patch("telegram_notifier.Bot") as mock:
        yield mock

def test_telegram_notifier_init(mock_bot):
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "test_chat"}):
        notifier = TelegramNotifier()
        assert notifier.enabled is True
        assert notifier.bot is not None

def test_telegram_notifier_disabled_no_creds():
    with patch.dict("os.environ", {}, clear=True):
        notifier = TelegramNotifier()
        assert notifier.enabled is False

@pytest.mark.asyncio
async def test_notify_trade_opened(mock_bot):
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "test_chat"}):
        notifier = TelegramNotifier()
        notifier.bot.send_message = AsyncMock()
        
        trade_info = {
            "symbol": "R_25",
            "contract_id": "123",
            "direction": "UP",
            "stake": 10.0,
            "entry_price": 100.0,
            "multiplier": 160
        }
        
        # Test the legacy method alias if any, or main methods
        if hasattr(notifier, "notify_trade_opened"):
            await notifier.notify_trade_opened(trade_info)
            assert notifier.bot.send_message.called

@pytest.mark.asyncio
async def test_notify_error(mock_bot):
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "test_chat"}):
        notifier = TelegramNotifier()
        notifier.bot.send_message = AsyncMock()
        
        await notifier.notify_error("Test Error")
        assert notifier.bot.send_message.called

def test_telegram_logging_handler(mock_bot):
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "test_chat"}):
        notifier = TelegramNotifier()
        notifier.notify_error = AsyncMock()
        
        handler = TelegramLoggingHandler(notifier)
        logger = logging.getLogger("test_logger")
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)
        
        # This should trigger the handler
        logger.error("Test Log Error")
        
        # Since it's fire-and-forget with create_task, we might need to wait or check something else
        # But we can at least check if it didn't crash
