"""
Conservative Risk Manager Wrapper
Wraps the existing risk_manager.py logic to implement the BaseRiskManager interface
"""

from base_risk_manager import BaseRiskManager
from risk_manager import RiskManager
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class ConservativeRiskManager(BaseRiskManager):
    """
    Wrapper for the existing conservative risk manager.
    Delegates to the original RiskManager implementation.
    """
    
    def __init__(self, user_id: str = None, overrides: Dict = None):
        """
        Initialize the conservative risk manager wrapper.
        
        Args:
            user_id: User identifier (for multi-tenant setups)
            overrides: User-specific parameter overrides (not used by conservative)
        """
        self.risk_manager = RiskManager()
        self.user_id = user_id
        logger.info(f"✅ Conservative risk manager wrapper initialized for user {user_id}")
    
    def can_trade(self) -> Tuple[bool, str]:
        """
        Check if trading is allowed.
        
        Returns:
            Tuple of (can_trade: bool, reason: str)
        """
        can_trade, reason = self.risk_manager.can_trade()
        return can_trade, reason
    
    def record_trade_opened(self, trade_info: Dict) -> None:
        """
        Record that a new trade has been opened.
        
        Args:
            trade_info: Dict containing trade details
        """
        self.risk_manager.record_trade_open(trade_info)
    
    def record_trade_closed(self, result: Dict) -> None:
        """
        Record that a trade has been closed.
        
        Args:
            result: Dict containing trade result
        """
        contract_id = result.get('contract_id')
        pnl = result.get('profit', 0.0)
        status = result.get('status', 'unknown')
        
        self.risk_manager.record_trade_close(
            contract_id=contract_id,
            pnl=pnl,
            status=status
        )
    
    def get_current_limits(self) -> Dict:
        """
        Get current risk parameters and limits.
        
        Returns:
            Dict of active thresholds and current counts
        """
        import config
        
        return {
            'max_concurrent_trades': config.MAX_CONCURRENT_TRADES,
            'current_concurrent_trades': len(self.risk_manager.active_trades),
            'max_trades_per_day': config.MAX_TRADES_PER_DAY,
            'daily_trade_count': len(self.risk_manager.trades_today),  # Fixed: use trades_today length
            'max_consecutive_losses': config.MAX_CONSECUTIVE_LOSSES,
            'consecutive_losses': self.risk_manager.consecutive_losses,
            'daily_pnl': self.risk_manager.daily_pnl,
            'cooldown_seconds': config.COOLDOWN_SECONDS,
        }
    
    def reset_daily_stats(self) -> None:
        """
        Reset daily statistics.
        """
        self.risk_manager.reset_daily_stats()
