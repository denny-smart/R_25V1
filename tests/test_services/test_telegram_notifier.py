import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram_notifier import TelegramNotifier
import asyncio

@pytest.fixture
def notifier(mock_env_vars):
    with patch("telegram.Bot") as mock_bot:
        n = TelegramNotifier()
        n.bot = MagicMock()
        n.bot.send_message = AsyncMock()
        return n

@pytest.mark.asyncio
async def test_notify_trade_open(notifier):
    """Test trade open notification"""
    trade_info = {
        'symbol': 'R_25',
        'direction': 'UP',
        'entry_price': 100.0,
        'stake': 10.0,
        'take_profit': 102.0,
        'stop_loss': 99.0
    }
    await notifier.notify_trade_open(trade_info)
    assert notifier.bot.send_message.called
    args, kwargs = notifier.bot.send_message.call_args
    assert "TRADE OPENED" in kwargs['text']
    assert "R_25" in kwargs['text']

@pytest.mark.asyncio
async def test_notify_trade_close(notifier):
    """Test trade close notification"""
    trade_info = {
        'symbol': 'R_25',
        'direction': 'UP',
        'entry_price': 100.0,
        'pnl': 5.0,
        'status': 'won',
        'exit_type': 'structure_tp'
    }
    # Pass trade_info as both result and trade_info to satisfy signature
    await notifier.notify_trade_close(trade_info, trade_info)
    assert notifier.bot.send_message.called
    args, kwargs = notifier.bot.send_message.call_args
    assert "TRADE CLOSED" in kwargs['text']
    assert "Net Result:" in kwargs['text']

@pytest.mark.asyncio
async def test_notify_error(notifier):
    """Test error notification"""
    await notifier.notify_error("System Failure")
    assert notifier.bot.send_message.called
    args, kwargs = notifier.bot.send_message.call_args
    assert "Error Detected" in kwargs['text']
    assert "System Failure" in kwargs['text']
