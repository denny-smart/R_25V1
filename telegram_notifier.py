"""
Telegram Notifier for Deriv R_25 Trading Bot
FIXED VERSION - Handles None values and cancellation phases
Sends trade notifications via Telegram
"""

import os
import asyncio
from typing import Dict, Optional
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
import config
from utils import setup_logger, format_currency

logger = setup_logger()

class TelegramNotifier:
    """Handles Telegram notifications for trading events"""
    
    def __init__(self):
        """Initialize Telegram notifier"""
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.bot = None
        self.enabled = False
        
        if self.bot_token and self.chat_id:
            try:
                self.bot = Bot(token=self.bot_token)
                self.enabled = True
                logger.info("✅ Telegram notifications enabled")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize Telegram bot: {e}")
                self.enabled = False
        else:
            logger.info("ℹ️ Telegram notifications disabled (no credentials)")
    
    def _safe_format(self, value, default: str = "N/A") -> str:
        """Safely format a value, handling None cases"""
        if value is None:
            return default
        try:
            if isinstance(value, (int, float)):
                return format_currency(value)
            return str(value)
        except Exception:
            return default
    
    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message via Telegram
        
        Args:
            message: Message text
            parse_mode: Parse mode (HTML or Markdown)
        
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            return True
        except TelegramError as e:
            logger.error(f"❌ Failed to send Telegram message: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Telegram error: {e}")
            return False
    
    async def notify_bot_started(self, balance: float):
        """Notify that bot has started"""
        if config.ENABLE_CANCELLATION:
            tp_text = f"Phase 2 TP: {config.POST_CANCEL_TAKE_PROFIT_PERCENT}%"
            sl_text = f"Phase 2 SL: {config.POST_CANCEL_STOP_LOSS_PERCENT}%"
            cancel_text = f"🛡️ Cancellation: {config.CANCELLATION_DURATION}s\n"
        else:
            tp_text = f"🎯 Take Profit: {config.TAKE_PROFIT_PERCENT}%"
            sl_text = f"🛑 Stop Loss: {config.STOP_LOSS_PERCENT}%"
            cancel_text = ""
        
        message = (
            "🤖 <b>Trading Bot Started</b>\n\n"
            f"💰 Balance: {format_currency(balance)}\n"
            f"📊 Symbol: {config.SYMBOL}\n"
            f"📈 Multiplier: {config.MULTIPLIER}x\n"
            f"💵 Stake: {format_currency(config.FIXED_STAKE)}\n"
            f"{cancel_text}"
            f"{tp_text}\n"
            f"{sl_text}\n"
            f"🔢 Max Daily Trades: {config.MAX_TRADES_PER_DAY}\n\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await self.send_message(message)
    
    async def notify_signal(self, signal: Dict):
        """Notify about trading signal"""
        direction = signal.get('signal', 'UNKNOWN')
        score = signal.get('score', 0)
        details = signal.get('details', {})
        
        if direction == 'HOLD':
            return  # Don't notify for HOLD signals
        
        emoji = "🟢" if direction == "BUY" else "🔴"
        
        # Safely get values with defaults
        rsi = details.get('rsi', 0)
        adx = details.get('adx', 0)
        atr_1m = details.get('atr_1m', 0)
        atr_5m = details.get('atr_5m', 0)
        
        message = (
            f"{emoji} <b>{direction} SIGNAL DETECTED</b>\n\n"
            f"📊 Score: {score}/{config.MINIMUM_SIGNAL_SCORE}\n"
            f"📈 RSI: {rsi:.2f}\n"
            f"💪 ADX: {adx:.2f}\n"
            f"📉 ATR 1m: {atr_1m:.4f}\n"
            f"📉 ATR 5m: {atr_5m:.4f}\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(message)
    
    async def notify_trade_opened(self, trade_info: Dict):
        """Notify that a trade has been opened"""
        direction = trade_info.get('direction', 'UNKNOWN')
        emoji = "🟢" if direction == "BUY" else "🔴"
        
        # Check if cancellation is enabled
        cancellation_enabled = trade_info.get('cancellation_enabled', False)
        
        message = (
            f"{emoji} <b>TRADE OPENED</b>\n\n"
            f"📍 Direction: <b>{direction}</b>\n"
            f"💰 Stake: {format_currency(trade_info.get('stake', 0))}\n"
            f"📈 Entry Price: {trade_info.get('entry_price', 0):.2f}\n"
            f"📊 Multiplier: {trade_info.get('multiplier', 0)}x\n"
        )
        
        # Add cancellation info or TP/SL based on mode
        if cancellation_enabled:
            cancel_fee = trade_info.get('cancellation_fee', config.CANCELLATION_FEE)
            cancel_expiry = trade_info.get('cancellation_expiry')
            
            message += (
                f"\n🛡️ <b>Phase 1: Cancellation Active</b>\n"
                f"⏱️ Duration: {config.CANCELLATION_DURATION}s\n"
                f"💰 Cancel Fee: {format_currency(cancel_fee)}\n"
            )
            
            if cancel_expiry:
                message += f"⏰ Expires: {cancel_expiry.strftime('%H:%M:%S')}\n"
        else:
            # Legacy mode with immediate TP/SL
            tp = trade_info.get('take_profit')
            sl = trade_info.get('stop_loss')
            
            if tp is not None:
                message += f"🎯 Take Profit: {format_currency(tp)}\n"
            if sl is not None:
                message += f"🛑 Stop Loss: {format_currency(sl)}\n"
        
        message += (
            f"\n🔑 Contract ID: <code>{trade_info.get('contract_id', 'N/A')}</code>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        
        await self.send_message(message)
    
    async def notify_trade_closed(self, result: Dict, trade_info: Dict):
        """Notify that a trade has been closed"""
        status = result.get('status', 'unknown')
        profit = result.get('profit', 0)
        
        # Determine emoji based on outcome
        if profit > 0:
            emoji = "✅"
            outcome = "WON"
        elif profit < 0:
            emoji = "❌"
            outcome = "LOST"
        else:
            emoji = "⚪"
            outcome = "CLOSED"
        
        direction = trade_info.get('direction', 'UNKNOWN')
        entry_price = trade_info.get('entry_price', 0)
        current_price = result.get('current_price', entry_price)
        
        # Safely calculate price change
        price_change = current_price - entry_price if current_price and entry_price else 0
        price_change_pct = (price_change / entry_price * 100) if entry_price > 0 else 0
        
        message = (
            f"{emoji} <b>TRADE {outcome}</b>\n\n"
            f"📍 Direction: <b>{direction}</b>\n"
            f"💰 P&L: <b>{format_currency(profit)}</b>\n"
            f"📈 Entry: {entry_price:.2f}\n"
            f"📉 Exit: {current_price:.2f}\n"
            f"📊 Change: {price_change:+.2f} ({price_change_pct:+.2f}%)\n"
            f"⏱️ Status: {status.upper()}\n"
            f"🔑 Contract: <code>{result.get('contract_id', 'N/A')}</code>\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(message)
    
    async def notify_daily_summary(self, stats: Dict):
        """Send daily trading summary"""
        win_rate = stats.get('win_rate', 0)
        total_pnl = stats.get('total_pnl', 0)
        
        emoji = "📊"
        if total_pnl > 0:
            emoji = "💰"
        elif total_pnl < 0:
            emoji = "📉"
        
        message = (
            f"{emoji} <b>DAILY SUMMARY</b>\n\n"
            f"📈 Total Trades: {stats.get('total_trades', 0)}\n"
            f"✅ Wins: {stats.get('winning_trades', 0)}\n"
            f"❌ Losses: {stats.get('losing_trades', 0)}\n"
            f"🎯 Win Rate: {win_rate:.1f}%\n"
            f"💰 Total P&L: <b>{format_currency(total_pnl)}</b>\n"
            f"📊 Today's Trades: {stats.get('trades_today', 0)}/{config.MAX_TRADES_PER_DAY}\n"
            f"💵 Daily P&L: {format_currency(stats.get('daily_pnl', 0))}\n"
        )
        
        # Add cancellation stats if enabled
        if config.ENABLE_CANCELLATION:
            message += (
                f"\n🛡️ Cancelled: {stats.get('trades_cancelled', 0)}\n"
                f"✅ Committed: {stats.get('trades_committed', 0)}\n"
            )
        
        message += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await self.send_message(message)
    
    async def notify_error(self, error_msg: str):
        """Notify about errors"""
        message = (
            f"⚠️ <b>ERROR ALERT</b>\n\n"
            f"❌ {error_msg}\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(message)
    
    async def notify_connection_lost(self):
        """Notify that connection was lost"""
        message = (
            "⚠️ <b>CONNECTION LOST</b>\n\n"
            "Attempting to reconnect...\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(message)
    
    async def notify_connection_restored(self):
        """Notify that connection was restored"""
        message = (
            "✅ <b>CONNECTION RESTORED</b>\n\n"
            "Bot is back online!\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(message)
    
    async def notify_bot_stopped(self, stats: Dict):
        """Notify that bot has stopped"""
        total_pnl = stats.get('total_pnl', 0)
        emoji = "💰" if total_pnl > 0 else "📉" if total_pnl < 0 else "📊"
        
        message = (
            f"🛑 <b>Trading Bot Stopped</b>\n\n"
            f"{emoji} Final P&L: <b>{format_currency(total_pnl)}</b>\n"
            f"📈 Total Trades: {stats.get('total_trades', 0)}\n"
            f"✅ Wins: {stats.get('winning_trades', 0)}\n"
            f"❌ Losses: {stats.get('losing_trades', 0)}\n"
            f"🎯 Win Rate: {stats.get('win_rate', 0):.1f}%\n"
        )
        
        # Add cancellation stats if enabled
        if config.ENABLE_CANCELLATION:
            message += (
                f"\n🛡️ Cancelled: {stats.get('trades_cancelled', 0)}\n"
                f"✅ Committed: {stats.get('trades_committed', 0)}\n"
            )
        
        message += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await self.send_message(message)

# Create global instance
notifier = TelegramNotifier()