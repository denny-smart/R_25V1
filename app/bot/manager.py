from typing import Dict, Optional
from app.bot.runner import BotRunner
import logging

logger = logging.getLogger(__name__)

class BotManager:
    """
    Manages multiple independent BotRunner instances for different users.
    Each user gets their own isolated bot instance with their own API token and state.
    """
    
    def __init__(self):
        # Map user_id -> BotRunner
        self._bots: Dict[str, BotRunner] = {}
        
    def get_bot(self, user_id: str) -> BotRunner:
        """
        Get or create a bot instance for the user.
        """
        if user_id not in self._bots:
            logger.info(f"Initializing new bot instance for user {user_id}")
            self._bots[user_id] = BotRunner(account_id=user_id)
            
        return self._bots[user_id]

    async def start_bot(self, user_id: str, api_token: Optional[str] = None) -> dict:
        """
        Start a bot for a specific user.
        If api_token is provided, it updates the bot's token.
        """
        bot = self.get_bot(user_id)
        return await bot.start_bot(api_token=api_token)

    async def stop_bot(self, user_id: str) -> dict:
        """
        Stop a specific user's bot.
        """
        if user_id in self._bots:
            return await self._bots[user_id].stop_bot()
        
        return {
            "success": False,
            "message": "Bot is not running",
            "status": "stopped"
        }
    
    async def restart_bot(self, user_id: str) -> dict:
        """
        Restart a specific user's bot.
        """
        if user_id in self._bots:
            return await self._bots[user_id].restart_bot()
            
        # If not in memory, try to start new one (requires ensuring token)
        # For restart, we assume it was running or exists.
        return {
            "success": False,
            "message": "Bot not found/not running",
            "status": "stopped"
        }

    def get_status(self, user_id: str) -> dict:
        """
        Get status for a specific user's bot.
        """
        if user_id in self._bots:
            return self._bots[user_id].get_status()
            
        return {
            "status": "stopped",
            "is_running": False,
            "uptime_seconds": None,
            "message": "Bot not initialized"
        }
        
    async def stop_all(self):
        """
        Stop all running bots (e.g. on server shutdown)
        """
        logger.info(f"Stopping all {len(self._bots)} active bots...")
        for user_id, bot in self._bots.items():
            if bot.is_running:
                await bot.stop_bot()

# Global instance
bot_manager = BotManager()
