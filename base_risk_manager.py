"""
Base Risk Manager Interface
Abstract base class that all risk managers must implement
"""

from abc import ABC, abstractmethod
from typing import Dict, Tuple


class BaseRiskManager(ABC):
    """
    Abstract base class defining the risk manager interface.
    All risk managers must implement these methods.
    """
    
    @abstractmethod
    def can_trade(self) -> Tuple[bool, str]:
        """
        Check if trading is allowed based on risk parameters.
        
        Returns:
            Tuple of (can_trade: bool, reason: str)
            - can_trade: True if allowed to open new trades
            - reason: Explanation if trading is blocked
        """
        pass
    
    @abstractmethod
    def record_trade_open(self, trade_info: Dict) -> None:
        """
        Record that a new trade has been opened.
        Updates internal counters and state.
        
        Args:
            trade_info: Dict containing trade details
                {
                    'contract_id': str,
                    'symbol': str,
                    'direction': str,
                    'stake': float,
                    'entry_price': float,
                    'take_profit': float,
                    'stop_loss': float
                }
        """
        pass
    
    @abstractmethod
    def record_trade_closed(self, result: Dict) -> None:
        """
        Record that a trade has been closed.
        Updates win/loss counters and P&L.
        
        Args:
            result: Dict containing trade result
                {
                    'contract_id': str,
                    'profit': float,
                    'status': str ('win', 'loss', 'breakeven')
                }
        """
        pass
    
    @abstractmethod
    def get_current_limits(self) -> Dict:
        """
        Get current risk parameters and limits.
        
        Returns:
            Dict of active thresholds and current counts:
            {
                'max_concurrent_trades': int,
                'current_concurrent_trades': int,
                'max_trades_per_day': int,
                'daily_trade_count': int,
                'max_consecutive_losses': int,
                'consecutive_losses': int,
                'daily_pnl': float,
                'max_daily_loss': float,
                'cooldown_seconds': int,
                ...
            }
        """
        pass
    
    @abstractmethod
    def reset_daily_stats(self) -> None:
        """
        Reset daily statistics at midnight.
        Called automatically by scheduler or manually.
        """
        pass
