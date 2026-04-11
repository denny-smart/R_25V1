"""Pydantic schemas for bot-related responses"""

from pydantic import BaseModel
from typing import Optional, Dict, List


class BotStatusResponse(BaseModel):
    status: str
    is_running: bool
    uptime_seconds: Optional[int] = None
    start_time: Optional[str] = None
    error_message: Optional[str] = None
    active_strategy: Optional[str] = None
    stake_amount: Optional[float] = None
    balance: Optional[float] = None
    profit: Optional[float] = None
    pnl: Optional[float] = None
    profit_percent: Optional[float] = None
    pnl_percent: Optional[float] = None
    active_positions: Optional[int] = 0
    win_rate: Optional[float] = 0.0
    trades_today: Optional[int] = 0
    active_trades: Optional[List[Dict]] = []
    active_trades_count: Optional[int] = 0
    statistics: Optional[Dict] = {}
    config: Optional[Dict] = {}


class BotControlResponse(BaseModel):
    success: bool
    message: str
    status: str
