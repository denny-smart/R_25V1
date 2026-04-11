from __future__ import annotations

from typing import Any, Dict, Optional
import logging

import config
from data_fetcher import DataFetcher

from app.core.deriv_api_key_crypto import decrypt_deriv_api_key
from app.core.supabase import supabase
from app.services.trades_service import UserTradesService

logger = logging.getLogger(__name__)


def load_user_deriv_api_key(user_id: str) -> Optional[str]:
    try:
        response = (
            supabase.table("profiles")
            .select("deriv_api_key")
            .eq("id", user_id)
            .single()
            .execute()
        )
        data = dict(response.data or {})
        encrypted_key = data.get("deriv_api_key")
        return decrypt_deriv_api_key(encrypted_key) if encrypted_key else None
    except Exception as exc:
        logger.warning("Failed to load Deriv API key for user %s: %s", user_id, exc)
        return None


async def fetch_live_balance(
    user_id: str, bot: Optional[Any] = None
) -> Optional[float]:
    fetcher = getattr(bot, "data_fetcher", None) if bot is not None else None

    if fetcher is not None and hasattr(fetcher, "get_balance"):
        try:
            ensure_connected = getattr(fetcher, "ensure_connected", None)
            if callable(ensure_connected):
                connected = await ensure_connected()
                if connected is False:
                    raise RuntimeError("existing data fetcher is disconnected")

            balance = await fetcher.get_balance()
            if balance is not None:
                return float(balance)
        except Exception as exc:
            logger.warning(
                "Failed to refresh live balance from running fetcher for user %s: %s",
                user_id,
                exc,
            )

    api_key = load_user_deriv_api_key(user_id)
    if not api_key:
        return None

    balance_fetcher = DataFetcher(
        api_token=api_key,
        app_id=str(getattr(config, "DERIV_APP_ID", "1089")),
    )

    try:
        connected = await balance_fetcher.connect()
        if not connected:
            return None
        balance = await balance_fetcher.get_balance()
        return float(balance) if balance is not None else None
    except Exception as exc:
        logger.warning("Failed to fetch live balance for user %s: %s", user_id, exc)
        return None
    finally:
        try:
            await balance_fetcher.disconnect()
        except Exception:
            pass


async def enrich_bot_status_snapshot(
    user_id: str,
    base_status: Optional[Dict[str, Any]],
    *,
    bot: Optional[Any] = None,
) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = dict(base_status or {})

    balance = await fetch_live_balance(user_id, bot=bot)
    if balance is not None:
        snapshot["balance"] = balance
        state = getattr(bot, "state", None)
        if state is not None and hasattr(state, "update_balance"):
            try:
                state.update_balance(balance)
            except Exception:
                pass

    persisted_stats = UserTradesService.get_user_stats(user_id)
    runtime_stats = snapshot.get("statistics")
    if isinstance(runtime_stats, dict) and runtime_stats:
        snapshot["statistics"] = {**persisted_stats, **runtime_stats}
    else:
        snapshot["statistics"] = persisted_stats

    active_trades = snapshot.get("active_trades")
    if not isinstance(active_trades, list):
        active_trades = UserTradesService.get_user_active_trades(user_id)
        snapshot["active_trades"] = active_trades

    snapshot["active_trades_count"] = len(active_trades)
    snapshot["active_positions"] = len(active_trades)

    if "stake_amount" not in snapshot:
        config_payload = snapshot.get("config")
        if isinstance(config_payload, dict):
            snapshot["stake_amount"] = config_payload.get("stake")

    if (
        "active_strategy" not in snapshot
        and bot is not None
        and getattr(bot, "strategy", None)
    ):
        try:
            snapshot["active_strategy"] = bot.strategy.get_strategy_name()
        except Exception:
            pass

    stats = snapshot["statistics"]
    if isinstance(stats, dict):
        snapshot["profit"] = stats.get("total_pnl", snapshot.get("profit", 0.0))
        snapshot["pnl"] = stats.get(
            "total_pnl", snapshot.get("pnl", snapshot.get("profit", 0.0))
        )
        snapshot["win_rate"] = stats.get("win_rate", snapshot.get("win_rate", 0.0))
        snapshot["trades_today"] = stats.get(
            "trades_today", snapshot.get("trades_today", stats.get("total_trades", 0))
        )

    snapshot.setdefault("balance", 0.0)
    snapshot.setdefault("statistics", {})
    snapshot.setdefault("active_trades", [])
    snapshot.setdefault("active_trades_count", 0)
    snapshot.setdefault("active_positions", 0)
    snapshot.setdefault("profit", 0.0)
    snapshot.setdefault("pnl", snapshot.get("profit", 0.0))
    snapshot.setdefault("win_rate", 0.0)

    return snapshot
