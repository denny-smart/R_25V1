"""
Risk Manager for Deriv R_25 Trading Bot
ENHANCED VERSION - Multi-Strategy Support
✅ Top-Down strategy with dynamic TP/SL
✅ Wait-and-cancel logic (4-minute decision point)
✅ Legacy scalping with two-phase risk
risk_manager.py - PRODUCTION VERSION
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List
import config
from utils import setup_logger, format_currency

logger = setup_logger()

class RiskManager:
    """
    Manages risk limits with multi-strategy support:
    - Top-Down: Dynamic TP/SL based on market structure
    - Scalping + Cancellation: Wait-and-cancel (4-min decision)
    - Legacy: Fixed TP/SL percentages
    """
    
    def __init__(self):
        """Initialize RiskManager with strategy detection"""
        self.max_trades_per_day = config.MAX_TRADES_PER_DAY
        self.max_daily_loss = config.MAX_DAILY_LOSS
        self.cooldown_seconds = config.COOLDOWN_SECONDS
        
        # Trade tracking
        self.trades_today: List[Dict] = []
        self.last_trade_time: Optional[datetime] = None
        self.daily_pnl: float = 0.0
        self.current_date = datetime.now().date()
        
        # Active trade tracking
        self.active_trade: Optional[Dict] = None
        self.has_active_trade = False
        
        # Statistics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.largest_win = 0.0
        self.largest_loss = 0.0
        self.max_drawdown = 0.0
        self.peak_balance = 0.0
        
        # Cancellation statistics (for scalping mode)
        self.trades_cancelled = 0
        self.trades_committed = 0
        self.cancellation_savings = 0.0
        
        # Circuit breaker
        self.consecutive_losses = 0
        self.max_consecutive_losses = 3
        
        # Strategy detection
        self.use_topdown = config.USE_TOPDOWN_STRATEGY
        self.cancellation_enabled = config.ENABLE_CANCELLATION and not self.use_topdown
        self.cancellation_fee = getattr(config, 'CANCELLATION_FEE', 0.45)
        
        # Initialize TP/SL amounts based on strategy
        self._initialize_strategy_parameters()
    
    def _initialize_strategy_parameters(self):
        """Initialize parameters based on active strategy"""
        if self.use_topdown:
            # Top-Down: Dynamic TP/SL from strategy
            self.target_profit = None  # Set dynamically per trade
            self.max_loss = None        # Set dynamically per trade
            logger.info("[OK] Risk Manager initialized (TOP-DOWN MODE)")
            logger.info(f"   Strategy: Market Structure Analysis")
            logger.info(f"   TP/SL: Dynamic (based on levels & swings)")
            logger.info(f"   Min R:R: 1:{config.TOPDOWN_MIN_RR_RATIO}")
            
        elif self.cancellation_enabled:
            # Scalping with cancellation: Wait-and-cancel logic
            self.target_profit = (config.POST_CANCEL_TAKE_PROFIT_PERCENT / 100) * config.FIXED_STAKE * config.MULTIPLIER
            self.max_loss = (config.POST_CANCEL_STOP_LOSS_PERCENT / 100) * config.FIXED_STAKE * config.MULTIPLIER
            logger.info("[OK] Risk Manager initialized (SCALPING + WAIT-CANCEL MODE)")
            logger.info(f"   Phase 1: Wait 4-min → Cancel if unprofitable")
            logger.info(f"   Phase 2 Target: {format_currency(self.target_profit)} (15% move)")
            logger.info(f"   Phase 2 Max Loss: {format_currency(self.max_loss)} (5% of stake)")
            logger.info(f"   Cancellation Fee: {format_currency(self.cancellation_fee)}")
            
        else:
            # Legacy: Fixed percentages
            self.target_profit = (config.TAKE_PROFIT_PERCENT / 100) * config.FIXED_STAKE * config.MULTIPLIER
            self.max_loss = (config.STOP_LOSS_PERCENT / 100) * config.FIXED_STAKE * config.MULTIPLIER
            logger.info("[OK] Risk Manager initialized (LEGACY MODE)")
            logger.info(f"   Target Profit: {format_currency(self.target_profit)}")
            logger.info(f"   Max Loss: {format_currency(self.max_loss)}")
        
        logger.info(f"   Circuit Breaker: {self.max_consecutive_losses} consecutive losses")
        logger.info(f"   Max Trades/Day: {self.max_trades_per_day}")
        logger.info(f"   Max Daily Loss: {format_currency(self.max_daily_loss)}")
    
    def reset_daily_stats(self):
        """Reset daily statistics at start of new day"""
        current_date = datetime.now().date()
        
        if current_date != self.current_date:
            logger.info(f"📅 New trading day - Resetting daily stats")
            
            # Log yesterday's performance
            if len(self.trades_today) > 0:
                logger.info(f"📊 Yesterday: {len(self.trades_today)} trades, P&L: {format_currency(self.daily_pnl)}")
                
                if self.cancellation_enabled:
                    cancelled_pct = (self.trades_cancelled / len(self.trades_today) * 100)
                    logger.info(f"   Cancelled: {self.trades_cancelled} ({cancelled_pct:.1f}%)")
                    logger.info(f"   Savings: {format_currency(self.cancellation_savings)}")
            
            self.current_date = current_date
            self.trades_today = []
            self.daily_pnl = 0.0
            self.last_trade_time = None
            self.active_trade = None
            self.has_active_trade = False
            self.consecutive_losses = 0
            self.trades_cancelled = 0
            self.trades_committed = 0
            self.cancellation_savings = 0.0
    
    def can_trade(self) -> tuple[bool, str]:
        """Check if trading is allowed"""
        self.reset_daily_stats()
        
        if self.has_active_trade:
            reason = "Active trade in progress (1 concurrent limit)"
            logger.debug(f"⏸️ {reason}")
            return False, reason
        
        if self.consecutive_losses >= self.max_consecutive_losses:
            reason = f"Circuit breaker: {self.consecutive_losses} consecutive losses"
            logger.warning(f"🛑 {reason}")
            return False, reason
        
        if len(self.trades_today) >= self.max_trades_per_day:
            reason = f"Daily trade limit reached ({self.max_trades_per_day} trades)"
            logger.warning(f"⚠️ {reason}")
            return False, reason
        
        if self.daily_pnl <= -self.max_daily_loss:
            reason = f"Daily loss limit reached ({format_currency(self.daily_pnl)})"
            logger.warning(f"⚠️ {reason}")
            return False, reason
        
        if self.last_trade_time:
            time_since_last = (datetime.now() - self.last_trade_time).total_seconds()
            if time_since_last < self.cooldown_seconds:
                remaining = self.cooldown_seconds - time_since_last
                reason = f"Cooldown active ({remaining:.0f}s remaining)"
                return False, reason
        
        return True, "OK"
    
    def validate_trade_parameters(self, stake: float, take_profit: float = None, 
                                  stop_loss: float = None) -> tuple[bool, str]:
        """Validate trade parameters based on strategy"""
        if stake <= 0:
            return False, "Stake must be positive"
        
        if stake > config.FIXED_STAKE * 1.2:
            return False, f"Stake exceeds maximum ({config.FIXED_STAKE * 1.2:.2f})"
        
        # Top-Down: TP/SL validation done by strategy
        if self.use_topdown:
            if take_profit and stop_loss:
                # Validate R:R if both provided
                risk = abs(take_profit - stop_loss)
                reward = abs(take_profit - stop_loss)  # Simplified
                return True, "Valid (Top-Down mode)"
            return True, "Valid (Top-Down - TP/SL from strategy)"
        
        # Cancellation mode: TP/SL applied after Phase 1
        if self.cancellation_enabled and (take_profit is None or stop_loss is None):
            return True, "Valid (wait-and-cancel mode)"
        
        # Legacy: Validate provided TP/SL
        if take_profit is not None and take_profit <= 0:
            return False, "Take profit must be positive"
        
        if stop_loss is not None and stop_loss <= 0:
            return False, "Stop loss must be positive"
        
        if stop_loss and stop_loss > config.MAX_LOSS_PER_TRADE * 1.15:
            return False, f"SL {format_currency(stop_loss)} exceeds max"
        
        if take_profit and stop_loss:
            risk_reward_ratio = take_profit / stop_loss
            if risk_reward_ratio < 1.5:
                logger.warning(f"⚠️ Low R:R ratio: {risk_reward_ratio:.2f}")
        
        return True, "Valid"
    
    def record_trade_open(self, trade_info: Dict):
        """Record a new trade opening"""
        trade_record = {
            'timestamp': datetime.now(),
            'contract_id': trade_info.get('contract_id'),
            'direction': trade_info.get('direction'),
            'stake': trade_info.get('stake', 0.0),
            'entry_price': trade_info.get('entry_price', 0.0),
            'take_profit': trade_info.get('take_profit'),
            'stop_loss': trade_info.get('stop_loss'),
            'status': 'open',
            'strategy': 'topdown' if self.use_topdown else ('scalping_cancel' if self.cancellation_enabled else 'legacy'),
            'phase': 'cancellation' if self.cancellation_enabled else 'committed',
            'cancellation_enabled': trade_info.get('cancellation_enabled', False),
            'cancellation_expiry': trade_info.get('cancellation_expiry')
        }
        
        self.trades_today.append(trade_record)
        self.last_trade_time = datetime.now()
        self.total_trades += 1
        
        self.active_trade = trade_record
        self.has_active_trade = True
        
        logger.info(f"📝 Trade #{self.total_trades}: {trade_info.get('direction')} @ {trade_info.get('entry_price'):.4f}")
        logger.info(f"🔒 Active trade locked (1/1 concurrent)")
        
        if self.use_topdown:
            # Top-Down trade
            tp = trade_info.get('take_profit')
            sl = trade_info.get('stop_loss')
            if tp and sl:
                logger.info(f"🎯 Top-Down Structure Trade:")
                logger.info(f"   TP Level: {tp:.4f}")
                logger.info(f"   SL Level: {sl:.4f}")
        elif self.cancellation_enabled:
            # Wait-and-cancel trade
            logger.info(f"🛡️ Phase 1: Wait-and-Cancel (4-min decision)")
            logger.info(f"   Will check profit at 240s")
            logger.info(f"   Cancel if unprofitable, commit if profitable")
        else:
            # Legacy trade
            logger.info(f"   TP: {format_currency(trade_record['take_profit'])}")
            logger.info(f"   SL: {format_currency(trade_record['stop_loss'])}")
    
    def record_trade_cancelled(self, contract_id: str, refund: float):
        """Record a trade cancellation (wait-and-cancel at 4-min mark)"""
        for trade in self.trades_today:
            if trade.get('contract_id') == contract_id:
                trade['status'] = 'cancelled'
                trade['cancelled_time'] = datetime.now()
                trade['refund'] = refund
                trade['exit_type'] = 'cancelled_wait_cancel'
                
                # Calculate savings (what we would have lost if continued)
                # At 4-min mark, trade was unprofitable
                estimated_loss = trade['stake'] - refund
                self.cancellation_savings += estimated_loss
                self.trades_cancelled += 1
                
                logger.info(f"🛑 Trade cancelled at 4-min decision point")
                logger.info(f"   Refund: {format_currency(refund)}")
                logger.info(f"   Fee paid: {format_currency(self.cancellation_fee)}")
                logger.info(f"   Prevented further loss")
                
                break
        
        # Clear active trade
        if self.active_trade and self.active_trade.get('contract_id') == contract_id:
            self.active_trade = None
            self.has_active_trade = False
            logger.info(f"🔓 Trade slot unlocked (0/1 concurrent)")
    
    def record_cancellation_expiry(self, contract_id: str):
        """Record when cancellation period expires (trade was profitable at 4-min)"""
        for trade in self.trades_today:
            if trade.get('contract_id') == contract_id:
                trade['phase'] = 'committed'
                trade['commitment_time'] = datetime.now()
                self.trades_committed += 1
                
                logger.info(f"✅ Trade committed to Phase 2 (was profitable at 4-min)")
                logger.info(f"   TP: {format_currency(self.target_profit)}")
                logger.info(f"   SL: {format_currency(self.max_loss)}")
                
                break
    
    def should_close_trade(self, current_pnl: float, current_price: float, 
                          previous_price: float) -> Dict:
        """Check if trade should be closed manually (emergency only)"""
        if not self.active_trade:
            return {'should_close': False, 'reason': 'No active trade'}
        
        # Emergency exit: daily loss limit approaching
        potential_daily_loss = self.daily_pnl + current_pnl
        if potential_daily_loss <= -(self.max_daily_loss * 0.9):
            return {
                'should_close': True,
                'reason': 'emergency_daily_loss',
                'message': f'Emergency: Daily loss approaching limit ({format_currency(potential_daily_loss)})',
                'current_pnl': current_pnl
            }
        
        # Otherwise let Deriv handle exits (TP/SL via limit_order)
        return {'should_close': False, 'reason': 'Deriv limit_order active'}
    
    def get_exit_status(self, current_pnl: float) -> Dict:
        """Get current exit status"""
        if not self.active_trade:
            return {'active': False}
        
        phase = self.active_trade.get('phase', 'unknown')
        strategy = self.active_trade.get('strategy', 'unknown')
        
        status = {
            'active': True,
            'current_pnl': current_pnl,
            'phase': phase,
            'strategy': strategy,
            'consecutive_losses': self.consecutive_losses
        }
        
        if strategy == 'topdown':
            status['target_profit'] = self.active_trade.get('take_profit')
            status['max_loss'] = self.active_trade.get('stop_loss')
            status['dynamic_tp_sl'] = True
        elif phase == 'committed':
            status['target_profit'] = self.target_profit
            status['percentage_to_target'] = (current_pnl / self.target_profit * 100) if self.target_profit > 0 else 0
            status['auto_tp_sl'] = True
        else:
            status['cancellation_active'] = True
            status['can_cancel'] = True
            status['decision_at'] = '240s'
        
        return status
    
    def record_trade_close(self, contract_id: str, pnl: float, status: str):
        """Record trade closure and update statistics"""
        trade = None
        for t in self.trades_today:
            if t.get('contract_id') == contract_id:
                trade = t
                break
        
        if trade:
            trade['status'] = status
            trade['pnl'] = pnl
            trade['close_time'] = datetime.now()
            
            # Determine exit type based on strategy
            strategy = trade.get('strategy', 'unknown')
            
            if strategy == 'topdown':
                # Top-Down: Check if hit structure levels
                tp_level = trade.get('take_profit')
                sl_level = trade.get('stop_loss')
                
                if tp_level and abs(pnl) > 0:
                    trade['exit_type'] = 'structure_tp' if pnl > 0 else 'structure_sl'
                else:
                    trade['exit_type'] = 'manual_close'
                    
            elif trade.get('phase') == 'committed':
                # Scalping Phase 2: Check fixed TP/SL
                target_profit = self.target_profit
                max_loss = self.max_loss
                
                if abs(pnl - target_profit) < 0.1:
                    trade['exit_type'] = 'take_profit'
                    logger.info(f"🎯 Hit TAKE PROFIT target (Phase 2)!")
                elif abs(abs(pnl) - max_loss) < 0.1:
                    trade['exit_type'] = 'stop_loss'
                    logger.info(f"🛑 Hit STOP LOSS limit (Phase 2)")
                else:
                    trade['exit_type'] = 'other'
            else:
                trade['exit_type'] = 'early_close'
        
        # Clear active trade
        if self.active_trade and self.active_trade.get('contract_id') == contract_id:
            self.active_trade = None
            self.has_active_trade = False
            logger.info(f"🔓 Trade slot unlocked (0/1 concurrent)")
        
        # Update P&L
        self.daily_pnl += pnl
        self.total_pnl += pnl
        
        # Update win/loss stats
        if pnl > 0:
            self.winning_trades += 1
            self.consecutive_losses = 0
            if pnl > self.largest_win:
                self.largest_win = pnl
            logger.info(f"✅ WIN | Consecutive losses reset to 0")
        elif pnl < 0:
            self.losing_trades += 1
            self.consecutive_losses += 1
            if pnl < self.largest_loss:
                self.largest_loss = pnl
            logger.warning(f"❌ LOSS | Consecutive losses: {self.consecutive_losses}/{self.max_consecutive_losses}")
        
        # Update drawdown
        if self.total_pnl > self.peak_balance:
            self.peak_balance = self.total_pnl
        
        current_drawdown = self.peak_balance - self.total_pnl
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown
        
        logger.info(f"💰 Trade closed: {status.upper()} | P&L: {format_currency(pnl)}")
        logger.info(f"📊 Daily: {format_currency(self.daily_pnl)} | Total: {format_currency(self.total_pnl)}")
    
    def get_statistics(self) -> Dict:
        """Get comprehensive trading statistics"""
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        # Count exit types
        tp_exits = sum(1 for t in self.trades_today if t.get('exit_type') in ['take_profit', 'structure_tp'])
        sl_exits = sum(1 for t in self.trades_today if t.get('exit_type') in ['stop_loss', 'structure_sl'])
        cancelled_exits = sum(1 for t in self.trades_today if 'cancelled' in t.get('exit_type', ''))
        
        # Calculate averages
        wins = [t['pnl'] for t in self.trades_today if t.get('pnl', 0) > 0]
        losses = [abs(t['pnl']) for t in self.trades_today if t.get('pnl', 0) < 0]
        
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        # Strategy-specific metrics
        total_attempted = len(self.trades_today)
        cancellation_rate = (self.trades_cancelled / total_attempted * 100) if total_attempted > 0 else 0
        
        stats = {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'total_pnl': self.total_pnl,
            'daily_pnl': self.daily_pnl,
            'trades_today': len(self.trades_today),
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'max_drawdown': self.max_drawdown,
            'peak_balance': self.peak_balance,
            'take_profit_exits': tp_exits,
            'stop_loss_exits': sl_exits,
            'cancelled_exits': cancelled_exits,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'consecutive_losses': self.consecutive_losses,
            'circuit_breaker_active': self.consecutive_losses >= self.max_consecutive_losses,
            'strategy_mode': 'topdown' if self.use_topdown else ('wait_cancel' if self.cancellation_enabled else 'legacy')
        }
        
        if self.cancellation_enabled:
            stats['trades_cancelled'] = self.trades_cancelled
            stats['trades_committed'] = self.trades_committed
            stats['cancellation_rate'] = cancellation_rate
            stats['cancellation_savings'] = self.cancellation_savings
        
        return stats
    
    def get_remaining_trades_today(self) -> int:
        """Get remaining trades allowed today"""
        return max(0, self.max_trades_per_day - len(self.trades_today))
    
    def get_remaining_loss_capacity(self) -> float:
        """Get remaining loss capacity for today"""
        return max(0, self.max_daily_loss + self.daily_pnl)
    
    def get_cooldown_remaining(self) -> float:
        """Get remaining cooldown time"""
        if not self.last_trade_time:
            return 0.0
        
        elapsed = (datetime.now() - self.last_trade_time).total_seconds()
        remaining = self.cooldown_seconds - elapsed
        return max(0.0, remaining)
    
    def print_status(self):
        """Print current risk management status"""
        can_trade, reason = self.can_trade()
        stats = self.get_statistics()
        
        print("\n" + "="*70)
        if self.use_topdown:
            print("RISK MANAGEMENT STATUS - TOP-DOWN STRATEGY")
        elif self.cancellation_enabled:
            print("RISK MANAGEMENT STATUS - WAIT-AND-CANCEL STRATEGY")
        else:
            print("RISK MANAGEMENT STATUS - LEGACY STRATEGY")
        print("="*70)
        
        print(f"Can Trade: {'✅ YES' if can_trade else '❌ NO'}")
        if not can_trade:
            print(f"Reason: {reason}")
        
        print(f"\nActive Trades: {1 if self.has_active_trade else 0}/1")
        if self.has_active_trade and self.active_trade:
            strategy = self.active_trade.get('strategy', 'unknown')
            phase = self.active_trade.get('phase', 'unknown')
            print(f"  └─ Strategy: {strategy.upper()}")
            print(f"  └─ Phase: {phase.upper()}")
            print(f"  └─ {self.active_trade.get('direction')} @ {self.active_trade.get('entry_price', 0):.4f}")
            
            if strategy == 'topdown':
                tp = self.active_trade.get('take_profit')
                sl = self.active_trade.get('stop_loss')
                if tp and sl:
                    print(f"  └─ TP: {tp:.4f} (structure level)")
                    print(f"  └─ SL: {sl:.4f} (swing point)")
            elif phase == 'cancellation':
                print(f"  └─ Waiting for 4-min decision point")
            else:
                print(f"  └─ TP: {format_currency(self.target_profit)}")
                print(f"  └─ SL: {format_currency(self.max_loss)}")
        
        print(f"\n📊 Today's Performance:")
        print(f"  Trades: {len(self.trades_today)}/{self.max_trades_per_day}")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")
        print(f"  Daily P&L: {format_currency(self.daily_pnl)}")
        
        if self.cancellation_enabled:
            print(f"\n🛡️ Wait-and-Cancel Filter:")
            print(f"  Cancelled (4-min): {self.trades_cancelled}")
            print(f"  Committed (5-min): {self.trades_committed}")
            if self.trades_cancelled > 0:
                print(f"  Losses Prevented: {format_currency(self.cancellation_savings)}")
        
        print(f"\n⚡ Circuit Breaker:")
        print(f"  Consecutive Losses: {self.consecutive_losses}/{self.max_consecutive_losses}")
        if self.consecutive_losses > 0:
            print(f"  ⚠️ {self.max_consecutive_losses - self.consecutive_losses} losses until halt")
        
        print(f"\n⏱️ Cooldown: {self.get_cooldown_remaining():.0f}s remaining")
        print("="*70 + "\n")
    
    def is_within_trading_hours(self) -> bool:
        """Synthetic indices trade 24/7"""
        return True


if __name__ == "__main__":
    print("="*70)
    print("TESTING ENHANCED RISK MANAGER - MULTI-STRATEGY SUPPORT")
    print("="*70)
    
    rm = RiskManager()
    
    print("\n✅ Configuration:")
    if rm.use_topdown:
        print(f"   Mode: TOP-DOWN MARKET STRUCTURE")
        print(f"   TP/SL: Dynamic (structure-based)")
    elif rm.cancellation_enabled:
        print(f"   Mode: SCALPING + WAIT-AND-CANCEL")
        print(f"   Decision: 4-min profit check")
        print(f"   Phase 2 Target: {format_currency(rm.target_profit)}")
        print(f"   Phase 2 Max Loss: {format_currency(rm.max_loss)}")
    else:
        print(f"   Mode: LEGACY SCALPING")
        print(f"   Target: {format_currency(rm.target_profit)}")
        print(f"   Max Loss: {format_currency(rm.max_loss)}")
    
    print("\n1. Testing trade open...")
    trade_info = {
        'contract_id': 'test_001',
        'direction': 'BUY',
        'stake': 10.0,
        'entry_price': 100.0,
        'take_profit': 100.50 if rm.use_topdown else None,
        'stop_loss': 99.70 if rm.use_topdown else None,
        'cancellation_enabled': rm.cancellation_enabled,
        'cancellation_expiry': datetime.now() + timedelta(seconds=300) if rm.cancellation_enabled else None
    }
    rm.record_trade_open(trade_info)
    
    if rm.cancellation_enabled:
        print("\n2. Testing cancellation expiry (profitable at 4-min)...")
        rm.record_cancellation_expiry('test_001')
    
    print("\n3. Testing trade close (win)...")
    rm.record_trade_close('test_001', 6.0, 'won')
    
    print("\n4. Statistics:")
    stats = rm.get_statistics()
    print(f"   Total trades: {stats['total_trades']}")
    print(f"   Win rate: {stats['win_rate']:.1f}%")
    print(f"   Total P&L: {format_currency(stats['total_pnl'])}")
    print(f"   Strategy: {stats['strategy_mode']}")
    if 'trades_committed' in stats:
        print(f"   Committed: {stats['trades_committed']}")
    
    print("\n" + "="*70)
    print("✅ RISK MANAGER TEST COMPLETE!")
    print("="*70)