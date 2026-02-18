"""
Rise/Fall Scalping Strategy Module
Self-contained module for Rise/Fall contract trading on synthetic indices
"""

from risefallbot.rf_strategy import RiseFallStrategy
from risefallbot.rf_risk_manager import RiseFallRiskManager

__all__ = ["RiseFallStrategy", "RiseFallRiskManager"]
