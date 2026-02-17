"""
Base Strategy Interface
Abstract base class that all trading strategies must implement
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd


class BaseStrategy(ABC):
    """
    Abstract base class defining the strategy interface.
    All strategies must implement these methods.
    """
    
    @abstractmethod
    def analyze(self, **kwargs) -> Optional[Dict]:
        """
        Analyze market data and return a trading signal.
        
        Args:
            **kwargs: Market data (varies by strategy - different timeframes needed)
        
        Returns:
            Dict with signal information if trade should be executed, None otherwise.
            Signal dict should contain:
            {
                'signal': 'UP' or 'DOWN',
                'symbol': str,
                'take_profit': float,
                'stop_loss': float,
                'risk_reward_ratio': float,
                'confidence': float (0-10),
                'reason': str (optional)
            }
        """
        pass
    
    @abstractmethod
    def get_required_timeframes(self) -> List[str]:
        """
        Get list of timeframes this strategy requires.
        
        Returns:
            List of timeframe strings (e.g., ['1w', '1d', '4h', '1h', '5m', '1m'])
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """
        Get the name/identifier of this strategy.
        
        Returns:
            Strategy name (e.g., 'Conservative', 'Scalping')
        """
        pass
