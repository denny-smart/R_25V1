"""
Configuration API Endpoints
Get and update bot configuration
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

import config
from app.schemas.common import ConfigResponse
from app.core.auth import get_current_active_user

router = APIRouter()

from app.core.supabase import supabase

@router.get("/current", response_model=ConfigResponse)
async def get_current_config(current_user: dict = Depends(get_current_active_user)):
    """Get current bot configuration"""
    
    # Fetch user specifics (deriv_api_key)
    deriv_api_key = None
    try:
        profile = supabase.table('profiles').select('deriv_api_key').eq('id', current_user['id']).single().execute()
        if profile.data and profile.data.get('deriv_api_key'):
            key = profile.data['deriv_api_key']
            # Mask the key (show last 4 chars if long enough)
            if len(key) > 4:
                deriv_api_key = f"*****{key[-4:]}"
            else:
                deriv_api_key = "*****"
    except Exception:
        pass

    return {
        "trading": {
            "symbol": config.SYMBOL,
            "multiplier": config.MULTIPLIER,
            "fixed_stake": config.FIXED_STAKE,
            "take_profit_percent": config.TAKE_PROFIT_PERCENT,
            "stop_loss_percent": config.STOP_LOSS_PERCENT,
        },
        "risk_management": {
            "max_trades_per_day": config.MAX_TRADES_PER_DAY,
            "max_daily_loss": config.MAX_DAILY_LOSS,
            "cooldown_seconds": config.COOLDOWN_SECONDS,
        },
        "strategy": {
            "rsi_buy_threshold": config.RSI_BUY_THRESHOLD,
            "rsi_sell_threshold": config.RSI_SELL_THRESHOLD,
            "adx_threshold": config.ADX_THRESHOLD,
            "minimum_signal_score": config.MINIMUM_SIGNAL_SCORE,
        },
        "deriv_api_key": deriv_api_key
    }

@router.put("/update")
async def update_config(
    updates: Dict[str, Any],
    current_user: dict = Depends(get_current_active_user)
):
    """
    Update bot configuration at runtime
    
    WARNING: Some changes require bot restart
    """
    try:
        updated_fields = []
        requires_restart = []
        
        # User-Specific Config (Supabase)
        if "deriv_api_key" in updates:
            new_key = updates["deriv_api_key"]
            # Save to Supabase profile
            supabase.table('profiles').update({
                "deriv_api_key": new_key
            }).eq("id", current_user["id"]).execute()
            
            updated_fields.append("deriv_api_key")
            # If the bot is running for this user, it might need restart, 
            # but for now we just save it. The BotManager will use it next start.
        
        # Trading config (Global/Shared for now - requires restart)
        if "fixed_stake" in updates:
            config.FIXED_STAKE = float(updates["fixed_stake"])
            updated_fields.append("fixed_stake")
            requires_restart.append("fixed_stake")
        
        # Risk management (can update live)
        if "max_trades_per_day" in updates:
            config.MAX_TRADES_PER_DAY = int(updates["max_trades_per_day"])
            updated_fields.append("max_trades_per_day")
        
        if "cooldown_seconds" in updates:
            config.COOLDOWN_SECONDS = int(updates["cooldown_seconds"])
            updated_fields.append("cooldown_seconds")
        
        return {
            "success": True,
            "updated_fields": updated_fields,
            "requires_restart": requires_restart,
            "message": "Configuration updated successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))