"""
Rise/Fall Bot Orchestrator — R_25 Support & Resistance edition.
Main async loop: fetches 1-minute OHLCV candles, detects S&R zones,
waits for confirmation candles, then executes 2-minute Rise/Fall contracts.

STRICT SINGLE-TRADE ENFORCEMENT:
    The scan loop is BLOCKED at the asyncio level whenever a trade is in
    its lifecycle.  Uses asyncio.Lock (trade_mutex) — not a boolean flag.
    A full 6-step lifecycle must complete before the next trade is considered.

rf_bot.py
"""

import asyncio
import os
import logging
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from pathlib import Path

from data_fetcher import DataFetcher
from risefallbot import rf_config
from risefallbot.rf_strategy import RiseFallStrategy
from risefallbot.rf_risk_manager import RiseFallRiskManager
from risefallbot.rf_trade_engine import RFTradeEngine
from app.core.deriv_api_key_crypto import (
    decrypt_deriv_api_key,
    encrypt_deriv_api_key,
    is_encrypted_deriv_api_key,
)

try:
    from telegram_notifier import notifier

    TELEGRAM_ENABLED = True
except ImportError:
    TELEGRAM_ENABLED = False

logger = logging.getLogger("risefallbot")

_running = False
_bot_task: Optional[asyncio.Task] = None
_running_by_user: Dict[str, bool] = {}
_bot_task_by_user: Dict[str, asyncio.Task] = {}
_decision_emit_state: Dict[str, Dict[str, Any]] = {}


def _state_key(user_id: Optional[str]) -> str:
    return str(user_id) if user_id else "__legacy__"


def _get_task_for_user(user_id: Optional[str]) -> Optional[asyncio.Task]:
    key = _state_key(user_id)
    if key == "__legacy__":
        return _bot_task
    return _bot_task_by_user.get(key)


def _set_task_for_user(user_id: Optional[str], task: asyncio.Task) -> None:
    global _bot_task
    key = _state_key(user_id)
    if key == "__legacy__":
        _bot_task = task
    else:
        _bot_task_by_user[key] = task


def _clear_task_for_user(
    user_id: Optional[str], task: Optional[asyncio.Task] = None
) -> None:
    global _bot_task
    key = _state_key(user_id)
    if key == "__legacy__":
        if task is None or _bot_task is task or (_bot_task and _bot_task.done()):
            _bot_task = None
        return
    existing = _bot_task_by_user.get(key)
    if task is None or existing is task or (existing and existing.done()):
        _bot_task_by_user.pop(key, None)


def _is_running_for_user(user_id: Optional[str]) -> bool:
    key = _state_key(user_id)
    if key == "__legacy__":
        return _running
    return _running_by_user.get(key, False)


def _set_running_for_user(user_id: Optional[str], running: bool) -> None:
    global _running
    key = _state_key(user_id)
    if key == "__legacy__":
        _running = running
        return
    if running:
        _running_by_user[key] = True
    else:
        _running_by_user.pop(key, None)


def _safe_user_component(user_id: Optional[str]) -> str:
    text = str(user_id) if user_id is not None else "anonymous"
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", text).strip("._")
    return cleaned or "anonymous"


# ── Logging infrastructure (unchanged from original) ────────────────────────

class _RFPerUserFileHandler(logging.Handler):
    def __init__(self, formatter: logging.Formatter):
        super().__init__(logging.DEBUG)
        self._formatter = formatter
        self._handlers: Dict[str, logging.Handler] = {}
        self._lock = threading.Lock()

    def _resolve_path(self, record: logging.LogRecord) -> str:
        user_key = _safe_user_component(getattr(record, "user_id", None))
        return str(Path("logs") / "risefall" / f"{user_key}.log")

    def _get_handler(self, path: str) -> logging.Handler:
        with self._lock:
            handler = self._handlers.get(path)
            if handler is None:
                target = Path(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                handler = logging.FileHandler(target, encoding="utf-8")
                handler.setLevel(logging.DEBUG)
                handler.setFormatter(self._formatter)
                self._handlers[path] = handler
            return handler

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if not hasattr(record, "user_id"):
                record.user_id = None
            self._get_handler(self._resolve_path(record)).emit(record)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        with self._lock:
            for handler in self._handlers.values():
                try:
                    handler.close()
                except Exception:
                    pass
            self._handlers.clear()
        super().close()


def _ensure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class _SafeConsoleFormatter(logging.Formatter):
    """Console formatter with optional ASCII-only output for stable log sinks."""

    def __init__(
        self, fmt: str, datefmt: Optional[str] = None, ascii_only: bool = True
    ):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._ascii_only = ascii_only

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        if self._ascii_only:
            rendered = rendered.encode("ascii", "ignore").decode("ascii")
        return rendered


def _setup_rf_logger():
    rf_root = logging.getLogger("risefallbot")
    if rf_root.handlers:
        return
    _ensure_utf8_stdio()
    rf_root.setLevel(getattr(logging, rf_config.RF_LOG_LEVEL, logging.INFO))
    rf_root.propagate = False  # ← isolate from multiplier bot logs

    # Add context filter for user_id injection.
    # IMPORTANT: attach to handlers too, because ancestor logger filters are not
    # applied to records emitted by child loggers.
    try:
        from app.core.logging import ContextInjectingFilter

        user_filter = ContextInjectingFilter()
    except Exception:

        class _DefaultUserFilter(logging.Filter):
            def filter(self, record):
                if not hasattr(record, "user_id"):
                    record.user_id = None
                return True
        user_filter = _DefaultUserFilter()

    rf_root.addFilter(user_filter)
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | [%(user_id)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    per_user_handler = _RFPerUserFileHandler(formatter)
    per_user_handler.addFilter(user_filter)
    rf_root.addHandler(per_user_handler)

    # Console handler (optional — useful during development)
    console_ascii_only = str(
        os.getenv("R50_CONSOLE_ASCII_ONLY", "1")
    ).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    console_formatter = _SafeConsoleFormatter(
        "%(asctime)s | %(name)s | %(levelname)s | [%(user_id)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        ascii_only=console_ascii_only,
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(console_formatter)
    ch.addFilter(user_filter)
    rf_root.addHandler(ch)

    # WebSocket handler (for live dashboard streaming) — added early
    try:
        from app.core.logging import WebSocketLoggingHandler

        ws_handler = WebSocketLoggingHandler()
        ws_handler.setFormatter(formatter)
        ws_handler.addFilter(user_filter)
        rf_root.addHandler(ws_handler)
    except Exception:
        pass


_setup_rf_logger()


# ── User config ──────────────────────────────────────────────────────────────

async def _fetch_user_config(user_id: Optional[str] = None) -> dict:
    result_config = {
        "api_token": os.getenv("DERIV_API_TOKEN"),
        "stake":     rf_config.RF_DEFAULT_STAKE,
    }
    try:
        from app.core.supabase import supabase

        base_query = supabase.table("profiles").select(
            "id, deriv_api_key, stake_amount"
        )
        if user_id:
            result = base_query.eq("id", user_id).single().execute()
            row = result.data if isinstance(result.data, dict) else None
        else:
            result = base_query.eq("active_strategy", "RiseFall").limit(1).execute()
            row = result.data[0] if result.data else None

        if row:
            if row.get("deriv_api_key"):
                stored_key = row["deriv_api_key"]
                result_config["api_token"] = decrypt_deriv_api_key(stored_key)
                if not is_encrypted_deriv_api_key(stored_key):
                    profile_id = row.get("id") or user_id
                    if profile_id:
                        try:
                            supabase.table("profiles").update(
                                {
                                    "deriv_api_key": encrypt_deriv_api_key(
                                        result_config["api_token"]
                                    )
                                }
                            ).eq("id", profile_id).execute()
                        except Exception as migration_error:
                            logger.warning(
                                f"Failed to auto-migrate plaintext Deriv API key for "
                                f"user {profile_id}: {migration_error}"
                            )
                logger.info("API token loaded from user profile")
            if row.get("stake_amount") is not None:
                result_config["stake"] = float(row["stake_amount"])
                logger.info(
                    f"💵 User stake loaded from profile: ${result_config['stake']}"
                )
    except Exception as e:
        logger.warning(f"Could not fetch user config from Supabase: {e}")
    return result_config


# ── Cross-process session lock ───────────────────────────────────────────────


async def _acquire_session_lock(user_id: str) -> bool:
    if not rf_config.RF_ENFORCE_DB_LOCK:
        logger.info(
            "[RF] DB session lock disabled (RF_ENFORCE_DB_LOCK=False) — skipping"
        )
        return True
    if not user_id:
        logger.error("[RF] _acquire_session_lock called with no user_id — aborting")
        return False
    try:
        from app.core.supabase import supabase
        ttl_seconds = max(1, int(getattr(rf_config, "RF_DB_LOCK_TTL_SECONDS", 900)))
        existing = (
            supabase.table("rf_bot_sessions")
            .select("user_id, started_at, process_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            started_at = row.get("started_at")
            should_reclaim = False
            if not started_at:
                should_reclaim = True
            else:
                try:
                    started_dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
                    if started_dt.tzinfo is None:
                        started_dt = started_dt.replace(tzinfo=timezone.utc)
                    age = datetime.now(timezone.utc) - started_dt
                    should_reclaim = age > timedelta(seconds=ttl_seconds)
                except Exception:
                    should_reclaim = True
            if should_reclaim:
                supabase.table("rf_bot_sessions").delete().eq("user_id", user_id).execute()
                logger.warning(f"[RF] Reclaimed stale DB session lock for user={user_id}")

        supabase.table("rf_bot_sessions").insert(
            {
                "user_id": user_id,
                "started_at": datetime.now().isoformat(),
                "process_id": os.getpid(),
            }
        ).execute()
        logger.info(
            f"[RF] ✅ DB session lock acquired for user={user_id} pid={os.getpid()}"
        )
        return True
    except Exception as e:
        err_str = str(e).lower()
        if any(
            x in err_str
            for x in [
                "duplicate",
                "unique",
                "conflict",
                "23505",  # duplicate key
                "invalid input syntax",
                "uuid",  # malformed UUID
            ]
        ):
            logger.warning(
                f"[RF] ⛔ DB session lock DENIED for user={user_id} — "
                f"another instance is already running or invalid user_id: {e}"
            )
        else:
            logger.error(f"[RF] ❌ DB session lock error for user={user_id}: {e}")
        return False


async def _release_session_lock(user_id: str) -> None:
    if not rf_config.RF_ENFORCE_DB_LOCK:
        return
    try:
        from app.core.supabase import supabase

        supabase.table("rf_bot_sessions").delete().eq("user_id", user_id).execute()
        logger.info(f"[RF] 🔓 DB session lock released for user={user_id}")
    except Exception as e:
        logger.error(
            f"[RF] ❌ Failed to release DB session lock for user={user_id}: {e}"
        )


async def _refresh_session_lock(user_id: str) -> None:
    if not rf_config.RF_ENFORCE_DB_LOCK or not user_id:
        return
    try:
        from app.core.supabase import supabase

        supabase.table("rf_bot_sessions").update(
            {
                "started_at": datetime.now().isoformat(),
                "process_id": os.getpid(),
            }
        ).eq("user_id", user_id).execute()
    except Exception as e:
        logger.warning(
            f"[RF] ⚠️ Failed to refresh DB session lock for user={user_id}: {e}"
        )


async def run(
    stake: Optional[float] = None,
    api_token: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """
    Main Rise/Fall bot entry point.

    Args:
        stake: User stake amount. If None, fetches from Supabase profiles table.
        api_token: Deriv API token. If None, fetches from Supabase profiles table.
        user_id: User ID for event broadcasting and DB persistence.

    - Creates its own DataFetcher (reuses the class, own WS connection)
    - Creates its own RFTradeEngine (independent WS connection)
    - Loops: fetch 1m candles → analyse → risk check → execute (strict 6-step lifecycle)

    CRITICAL: Prevents duplicate instances per user/task key.
    Different users can run concurrently; same user is guarded.
    """
    from app.core.context import user_id_var, bot_type_var

    user_id_var.set(user_id)
    bot_type_var.set("risefall")

    existing_task = _get_task_for_user(user_id)
    if existing_task and not existing_task.done():
        logger.warning(
            f"[RF] Duplicate start ignored — bot already running for user={user_id}."
        )
        return

    current_task = asyncio.current_task()
    if current_task:
        _set_task_for_user(user_id, current_task)
    logger.info(f"[RF] ✅ Registered bot task for user={user_id}: {current_task}")

    # Lazy import to avoid circular imports at module level
    from app.bot.events import event_manager
    from app.services.trades_service import UserTradesService

    logger.info("[RF] Rise/Fall S&R bot starting (R_25 | 1m candles | 2m contracts)")
    logger.info("[RF] Strict single-trade enforcement enabled (asyncio.Lock mutex)")

    user_cfg = await _fetch_user_config(user_id=user_id)
    if stake is None:
        stake = user_cfg["stake"]
    if api_token is None:
        api_token = user_cfg["api_token"]

    if not api_token:
        logger.error(
            "❌ No API token found (profile or DERIV_API_TOKEN env) — cannot start Rise/Fall bot"
        )
        await event_manager.broadcast(
            {
                "type": "error",
                "message": "Rise/Fall startup failed: missing API token",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        await event_manager.broadcast(
            {
                "type": "bot_status",
                "status": "stopped",
                "message": "Rise/Fall bot not started: missing API token",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        _clear_task_for_user(user_id, current_task)
        return

    strategy    = RiseFallStrategy()
    risk_manager = RiseFallRiskManager()
    data_fetcher = DataFetcher(api_token, rf_config.RF_APP_ID)
    trade_engine = RFTradeEngine(api_token, rf_config.RF_APP_ID)

    if not await data_fetcher.connect():
        logger.error("❌ DataFetcher connection failed — aborting")
        await event_manager.broadcast(
            {
                "type": "error",
                "message": "Rise/Fall startup failed: market data connection failed",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        await event_manager.broadcast(
            {
                "type": "bot_status",
                "status": "stopped",
                "message": "Rise/Fall bot not started: data connection failed",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        _clear_task_for_user(user_id, current_task)
        return

    if not await trade_engine.connect():
        logger.error("[RF] RFTradeEngine connection failed — aborting")
        await data_fetcher.disconnect()
        await event_manager.broadcast(
            {
                "type": "error",
                "message": "Rise/Fall startup failed: trade engine connection failed",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        await event_manager.broadcast(
            {
                "type": "bot_status",
                "status": "stopped",
                "message": "Rise/Fall bot not started: trade engine connection failed",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        _clear_task_for_user(user_id, current_task)
        return

    balance = await data_fetcher.get_balance()
    if balance:
        logger.info(f"[RF] Account Balance: ${balance:.2f}")
        if TELEGRAM_ENABLED:
            try:
                await notifier.notify_bot_started(
                    balance,
                    stake,
                    "Rise/Fall Scalping",
                    symbol_count=len(rf_config.RF_SYMBOLS),
                )
            except Exception as e:
                logger.error(f"[RF] Telegram notification failed: {e}")

    logger.info(
        f"[RF] Config | symbol=R_25 scan={rf_config.RF_SCAN_INTERVAL}s "
        f"stake=${stake} contract={rf_config.RF_CONTRACT_DURATION}{rf_config.RF_DURATION_UNIT} "
        f"sr_candles={rf_config.RF_SR_CANDLE_COUNT} pivot_window={rf_config.RF_SR_PIVOT_WINDOW}"
    )

    _set_running_for_user(user_id, True)
    cycle = 0
    _start_time = datetime.now()
    _current_balance = balance or 0.0

    # Startup ghost cleanup
    if risk_manager.trade_mutex.locked():
        logger.warning("[RF] STARTUP LOCK DETECTED — performing ghost cleanup...")
        if len(risk_manager.active_trades) == 0:
            logger.warning("[RF] Ghost mutex — force-releasing lock")
            if risk_manager.trade_mutex.locked():
                risk_manager._trade_mutex.release()
                risk_manager._trade_lock_active = False
                risk_manager._locked_symbol = None
                risk_manager._locked_trade_info = {}
            if risk_manager.is_halted():
                risk_manager.clear_halt()
            logger.info("[RF] Startup cleanup complete")

    # Broadcast bot_status → running with all fields the frontend expects
    await event_manager.broadcast(
        {
            "type": "bot_status",
            "status": "running",
            "active_strategy": "RiseFall",
            "stake_amount": stake,
            "uptime_seconds": 0,
            "balance": _current_balance,
            "active_positions": 0,
            "win_rate": 0,
            "trades_today": 0,
            "profit": 0,
            "message": f"Rise/Fall bot started – scanning {len(rf_config.RF_SYMBOLS)} symbols",
            "symbols": rf_config.RF_SYMBOLS,
            "account_id": user_id,
        }
    )

    initial_stats = risk_manager.get_statistics()
    await event_manager.broadcast(
        {
            "type": "statistics",
            "stats": initial_stats,
            "strategy": "RiseFall",
            "timestamp": datetime.now().isoformat(),
            "account_id": user_id,
        }
    )

    try:
        while _is_running_for_user(user_id):
            cycle += 1
            await _refresh_session_lock(user_id)
            logger.debug(f"[RF] Cycle #{cycle} | {datetime.now().strftime('%H:%M:%S')}")

            risk_manager.ensure_daily_reset_if_needed()

            # ─────────────────────────────────────────────────────────────────────
            # WATCHDOG: Detect ghost mutex — held with no real active trades
            # Runs every cycle so it fires even when no new trade is being acquired
            # PRIORITY 4 FIX: Guard with datetime.min check to prevent false trigger on startup
            # ─────────────────────────────────────────────────────────────────────
            if (
                risk_manager.trade_mutex.locked()
                and len(risk_manager.active_trades) == 0
            ):
                # _pending_entry_timestamp initializes to datetime.min, which would cause
                # elapsed time to be astronomically large and trigger false watchdog on startup
                if risk_manager._pending_entry_timestamp != datetime.min:
                    elapsed = (
                        datetime.now() - risk_manager._pending_entry_timestamp
                    ).total_seconds()
                else:
                    elapsed = 0.0

                if elapsed > rf_config.RF_PENDING_TIMEOUT_SECONDS:
                    logger.warning(
                        f"[RF] WATCHDOG: Mutex held {elapsed:.0f}s with no active trades — "
                        "force-releasing ghost lock"
                    )
                    risk_manager._trade_mutex.release()
                    risk_manager._trade_lock_active = False
                    risk_manager._locked_symbol = None
                    risk_manager._locked_trade_info = {}
                    if risk_manager.is_halted():
                        risk_manager.clear_halt()
                    logger.info(
                        "[RF] ✅ WATCHDOG RECOVERY COMPLETE: Ghost lock released — resuming scan"
                    )

            # Auto-recovery: halted with no active trades
            if risk_manager.is_halted() and len(risk_manager.active_trades) == 0:
                logger.warning(
                    f"[RF] AUTO-RECOVERY: Clearing halt — no active trades. "
                    f"Was: {risk_manager._halt_reason}"
                )
                risk_manager.clear_halt()
                await event_manager.broadcast(
                    {
                        "type": "bot_status",
                        "status": "running",
                        "message": "🔄 System recovered from halt — resuming normal operation",
                        "timestamp": datetime.now().isoformat(),
                        "account_id": user_id,
                    }
                )

            if risk_manager.is_halted():
                elapsed = (
                    datetime.now() - risk_manager._halt_timestamp
                ).total_seconds()
                logger.error(
                    f"[RF] SYSTEM HALTED | Reason: {risk_manager._halt_reason} | "
                    f"Duration: {elapsed:.0f}s"
                )
                await _broadcast_rf_decision(
                    event_manager, user_id, "SYSTEM", "risk", "system_locked",
                    reason=f"System locked: {risk_manager._halt_reason}",
                    details={"duration_seconds": int(elapsed)},
                    severity="error", min_interval_seconds=10,
                )
                await event_manager.broadcast(
                    {
                        "type": "bot_status",
                        "status": "running",
                        "message": (
                            f"🚨 SYSTEM LOCKED: {risk_manager._halt_reason}. "
                            "Scanning paused until lock clears."
                        ),
                        "timestamp": datetime.now().isoformat(),
                        "account_id": user_id,
                    }
                )
            elif risk_manager.is_trade_active():
                active_info     = risk_manager.get_active_trade_info()
                active_symbol   = active_info.get("symbol", "unknown")
                active_contract = active_info.get("contract_id", "unknown")
                logger.warning(
                    f"[RF] TRADE LOCKED — {active_symbol}#{active_contract} in lifecycle | "
                    "Skipping scan until lifecycle completes"
                )
                await _broadcast_rf_decision(
                    event_manager, user_id, active_symbol, "monitoring",
                    "lifecycle_active",
                    reason=f"Monitoring {active_symbol}#{active_contract}",
                    details={"contract_id": active_contract},
                    min_interval_seconds=10,
                )

            else:
                cycle_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    f"[RF] CYCLE #{cycle} | {cycle_ts} | "
                    "Scanning R_25 for S&R zone opportunities"
                )
                await _broadcast_rf_decision(
                    event_manager, user_id, "R_25", "scan",
                    "checking_opportunities",
                    reason="Checking R_25 for S&R zone touch + confirmation",
                    details={"cycle": cycle},
                    min_interval_seconds=0,
                )

                async def _process_symbol_safe(symbol: str):
                    try:
                        logger.info(
                            f"[RF][{symbol}] SCAN | Checking trading opportunities"
                        )
                        await _process_symbol(
                            symbol, strategy, risk_manager,
                            data_fetcher, trade_engine,
                            stake, user_id, event_manager, UserTradesService,
                        )
                    except Exception as e:
                        logger.error(f"[RF][{symbol}] ERROR: {e}")

                tasks = [
                    asyncio.create_task(_process_symbol_safe(sym))
                    for sym in rf_config.RF_SYMBOLS
                ]
                if tasks:
                    await asyncio.gather(*tasks)

            # Log summary
            stats = risk_manager.get_statistics()
            logger.debug(
                f"[RF] Cycle #{cycle} done | "
                f"trades={stats['trades_today']} W={stats['wins']} L={stats['losses']} "
                f"pnl={stats['total_pnl']:+.2f}"
            )

            # Broadcast statistics after each cycle
            await event_manager.broadcast(
                {
                    "type": "statistics",
                    "stats": stats,
                    "timestamp": datetime.now().isoformat(),
                    "account_id": user_id,
                }
            )

            try:
                fresh_balance = await data_fetcher.get_balance()
                if fresh_balance is not None:
                    _current_balance = fresh_balance
            except Exception:
                pass

            uptime_secs = int((datetime.now() - _start_time).total_seconds())
            await event_manager.broadcast(
                {
                    "type": "bot_status",
                    "status": "running",
                    "active_strategy": "RiseFall",
                    "stake_amount": stake,
                    "uptime_seconds": uptime_secs,
                    "balance": _current_balance,
                    "active_positions": stats.get("active_positions", 0),
                    "win_rate": stats.get("win_rate", 0),
                    "trades_today": stats.get("trades_today", 0),
                    "profit": stats.get("total_pnl", 0),
                    "account_id": user_id,
                }
            )

            await asyncio.sleep(rf_config.RF_SCAN_INTERVAL)

    except asyncio.CancelledError:
        logger.info("[RF] Bot cancelled")
    except Exception as e:
        logger.error(f"❌ Rise/Fall bot fatal error: {e}")
        await event_manager.broadcast(
            {
                "type": "error",
                "message": f"Rise/Fall fatal error: {e}",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
    finally:
        _set_running_for_user(user_id, False)
        _clear_task_for_user(user_id, asyncio.current_task())

        # Emergency record for mid-lifecycle cancellation
        if risk_manager.trade_mutex.locked() and len(risk_manager.active_trades) > 0:
            first_trade   = list(risk_manager.active_trades.values())[0]
            emergency_cid = first_trade.get("contract_id", "unknown")
            emergency_sym = first_trade.get("symbol", "unknown")
            logger.critical(
                f"[RF] BOT CANCELLED MID-LIFECYCLE — contract={emergency_cid} "
                f"symbol={emergency_sym} | Writing emergency DB record"
            )
            if user_id:
                try:
                    from app.services.trades_service import UserTradesService

                    UserTradesService.save_trade(user_id, {
                        "contract_id": emergency_cid,
                        "symbol": emergency_sym,
                        "signal": first_trade.get("direction", "unknown"),
                        "stake": first_trade.get("stake", 0),
                        "profit": 0,
                        "status": "unknown",
                        "duration": 0,
                        "strategy_type": "RiseFall",
                        "closure_reason": "bot_cancelled",
                        "timestamp":     datetime.now().isoformat(),
                    })
                    logger.info(f"[RF] Emergency DB record written for {emergency_cid}")
                except Exception as db_err:
                    logger.error(f"[RF] Emergency DB write FAILED for {emergency_cid}: {db_err}")

        if risk_manager.trade_mutex.locked():
            risk_manager.release_trade_lock(reason="bot shutdown — forced cleanup")

        await data_fetcher.disconnect()
        await trade_engine.disconnect()
        await _release_session_lock(user_id)

        stop_message = "Rise/Fall bot stopped"
        if risk_manager.is_halted():
            stop_message = f"Rise/Fall bot stopped with active lock: {risk_manager._halt_reason}"
        logger.info(f"[RF] {stop_message}")

        if TELEGRAM_ENABLED:
            try:
                await notifier.notify_bot_stopped(risk_manager.get_statistics())
            except Exception as e:
                logger.error(f"[RF] Telegram notification failed: {e}")

        # Broadcast bot_status → stopped
        await event_manager.broadcast(
            {
                "type": "bot_status",
                "status": "stopped",
                "message": stop_message,
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )


def stop(user_id: Optional[str] = None):
    global _running
    _running = False
    if user_id is None:
        for key in list(_running_by_user.keys()):
            _running_by_user[key] = False
        logger.info("[RF] Stop requested for all users")
        return
    _set_running_for_user(user_id, False)
    logger.info(f"[RF] Stop requested for user={user_id}")


# ── Symbol processor ─────────────────────────────────────────────────────────

async def _process_symbol(
    symbol: str,
    strategy: RiseFallStrategy,
    risk_manager: RiseFallRiskManager,
    data_fetcher: DataFetcher,
    trade_engine: RFTradeEngine,
    stake: float,
    user_id: Optional[str],
    event_manager,
    UserTradesService,
):
    """
    Full 6-step lifecycle for one symbol scan:
      1.  Fetch 1-minute OHLCV candles.
      2.  Run S&R zone analysis + confirmation check.
      3.  Gate through risk manager.
      4.  Acquire trade lock and execute contract.
      5.  Monitor until settlement.
      6.  Write result to DB and release lock.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        f"[RF][{symbol}] SCAN | {ts} | "
        f"Fetching {rf_config.RF_SR_CANDLE_COUNT} x 1m candles for S&R analysis"
    )

    # ── STEP 1: Fetch 1-minute candles ───────────────────────────────────
    candle_data = await data_fetcher.fetch_candles(
        symbol=symbol,
        interval=rf_config.RF_CANDLE_INTERVAL_MINUTES,
        count=rf_config.RF_SR_CANDLE_COUNT,
    )

    # Fallback: if data_fetcher does not yet expose fetch_candles, try
    # the generic method names used by other strategies.
    if candle_data is None or (hasattr(candle_data, "empty") and candle_data.empty):
        for method_name in ("fetch_ohlcv", "fetch_1m_candles", "get_candles"):
            method = getattr(data_fetcher, method_name, None)
            if method:
                try:
                    candle_data = await method(
                        symbol, count=rf_config.RF_SR_CANDLE_COUNT,
                        interval=rf_config.RF_CANDLE_INTERVAL_MINUTES,
                    )
                    if candle_data is not None and not (
                        hasattr(candle_data, "empty") and candle_data.empty
                    ):
                        break
                except Exception as fe:
                    logger.debug(f"[RF][{symbol}] {method_name} failed: {fe}")

    if candle_data is None or (hasattr(candle_data, "empty") and candle_data.empty):
        logger.warning(f"[RF][{symbol}] No candle data returned")
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "data", "no_trade",
            reason="No 1-minute candle data returned",
            details={"candles_requested": rf_config.RF_SR_CANDLE_COUNT},
            severity="warning",
        )
        return

    # ── STEP 2: Strategy analysis ─────────────────────────────────────────
    signal = strategy.analyze(data_1m=candle_data, symbol=symbol, stake=stake)

    if signal is None:
        analysis_meta = {}
        if hasattr(strategy, "get_last_analysis"):
            try:
                analysis_meta = strategy.get_last_analysis(symbol) or {}
            except Exception:
                analysis_meta = {}

        skip_reason  = analysis_meta.get("reason") or "Strategy conditions not met"
        skip_code    = analysis_meta.get("code")   or "strategy_conditions_not_met"
        skip_details = (
            analysis_meta.get("details")
            if isinstance(analysis_meta.get("details"), dict)
            else {}
        )

        logger.info(
            f"[RF][{symbol}] SCAN | No opportunity: {skip_reason} (code={skip_code})"
        )
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "signal", "no_trade",
            reason=skip_reason,
            details={"mode": "sr_confirmation", "skip_code": skip_code, **skip_details},
        )
        return

    if hasattr(risk_manager, "note_qualifying_signal"):
        try:
            risk_manager.note_qualifying_signal(symbol, signal)
        except Exception as exc:
            logger.warning(
                f"[RF][{symbol}] Failed to register qualifying signal: {exc}"
            )

    direction     = signal["direction"]
    stake_val     = signal["stake"]
    duration      = signal["duration"]
    duration_unit = signal["duration_unit"]

    execution_reason = (
        f"S&R {signal.get('zone_type','?')} zone (level={signal.get('zone_level','?')}) "
        f"| pattern={signal.get('confirmation_pattern','?')} "
        f"| {signal.get('trade_label','?')} ({direction})"
    )

    logger.info(
        f"[RF][{symbol}] Opportunity detected | "
        f"zone={signal.get('zone_type')} @ {signal.get('zone_level')} "
        f"pattern={signal.get('confirmation_pattern')} "
        f"direction={direction} stake=${stake_val} "
        f"duration={duration}{duration_unit}"
    )

    # ── STEP 3: Risk gate ─────────────────────────────────────────────────
    can_trade, reason = risk_manager.can_trade(symbol=symbol, stake=stake_val)
    if not can_trade:
        logger.info(f"[RF][{symbol}] Cannot trade: {reason}")
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "risk", "no_trade",
            reason=reason,
            details={
                "gate": "can_trade", "skip_code": reason,
                "direction": direction,
                "trade_label": signal.get("trade_label"),
            },
            severity="warning",
        )
        return

    max_stake = getattr(rf_config, "RF_MAX_STAKE", 100.0)
    if stake_val > max_stake:
        logger.warning(f"[RF][{symbol}] Stake ${stake_val} exceeds max ${max_stake}")
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "risk", "no_trade",
            reason=f"Stake ${stake_val:.2f} exceeds max ${max_stake:.2f}",
            details={"stake": stake_val, "max_stake": max_stake},
            severity="warning",
        )
        return

    await _broadcast_rf_decision(
        event_manager, user_id, symbol, "signal", "opportunity_detected",
        reason=f"S&R {signal.get('zone_type')} zone touch confirmed "
               f"({signal.get('confirmation_pattern')})",
        details={
            "direction":            direction,
            "trade_label":          signal.get("trade_label"),
            "zone_type":            signal.get("zone_type"),
            "zone_level":           signal.get("zone_level"),
            "confirmation_pattern": signal.get("confirmation_pattern"),
            "stake":                stake_val,
            "confidence":           signal.get("confidence"),
        },
        min_interval_seconds=0,
    )

    # ── STEP 4: Acquire trade lock ────────────────────────────────────────
    lock_acquired = await risk_manager.acquire_trade_lock(
        symbol, "pending", stake=stake_val, wait_for_lock=False,
    )
    if not lock_acquired:
        logger.error(f"[RF][{symbol}] Could not acquire trade lock")
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "risk", "no_trade",
            reason="trade_lock_active", details={"gate": "trade_lock"},
            severity="warning",
        )
        return

    pnl = 0.0

    try:
        await event_manager.broadcast(
            {
                "type": "signal",
                "symbol": symbol,
                "signal": direction,
                "strategy": "RiseFall",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )

        if TELEGRAM_ENABLED:
            try:
                await notifier.notify_signal({
                    "signal": direction, "symbol": symbol,
                    "score":  signal.get("confidence", 5),
                    "stake":  stake_val, "duration": duration,
                    "duration_unit": duration_unit, "strategy_type": "RiseFall",
                    "user_id": user_id, "execution_reason": execution_reason,
                    "details": {
                        "trade_label":          signal.get("trade_label"),
                        "zone_type":            signal.get("zone_type"),
                        "zone_level":           signal.get("zone_level"),
                        "confirmation_pattern": signal.get("confirmation_pattern"),
                    },
                })
            except Exception as e:
                logger.error(f"[RF] Telegram signal notification failed: {e}")

        if len(risk_manager.active_trades) > 0:
            logger.critical(
                f"[RF][{symbol}] DEFENSIVE BLOCK: "
                f"active_trades={len(risk_manager.active_trades)}"
            )
            return

        logger.info(
            f"[RF] STEP 2/6 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"EXECUTING {symbol} {direction} ${stake_val} "
            f"duration={duration}{duration_unit}"
        )
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "execution", "opportunity_taken",
            reason="Lock acquired — executing contract",
            details={"direction": direction, "stake": stake_val},
            min_interval_seconds=0,
        )

        result = await trade_engine.buy_rise_fall(
            symbol=symbol, direction=direction, stake=stake_val,
            duration=duration, duration_unit=duration_unit,
        )

        if not result:
            logger.error(f"[RF][{symbol}] Trade execution failed")
            await _broadcast_rf_decision(
                event_manager, user_id, symbol, "execution", "opportunity_failed",
                reason="Trade engine buy request failed",
                severity="error", min_interval_seconds=0,
            )
            risk_manager.halt(f"Trade execution failed for {symbol} {direction}")
            await event_manager.broadcast(
                {
                    "type": "error",
                    "message": f"Trade execution failed for {symbol} - system halted",
                    "timestamp": datetime.now().isoformat(),
                    "account_id": user_id,
                }
            )
            return

        contract_id = result["contract_id"]
        logger.info(
            f"[RF] STEP 2/6 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"EXECUTION CONFIRMED {symbol}#{contract_id}"
        )

        risk_manager._locked_trade_info = {"contract_id": contract_id, "symbol": symbol}

        risk_manager.record_trade_open(
            {
                "contract_id": contract_id,
                "symbol": symbol,
                "direction": direction,
                "stake": stake_val,
            }
        )

        await event_manager.broadcast(
            {
                "type": "trade_lock_active",
                "symbol": symbol,
                "contract_id": contract_id,
                "message": f"Trade LOCKED on {symbol} - full lifecycle active",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )

        await event_manager.broadcast(
            {
                "type": "trade_opened",
                "symbol": symbol,
                "direction": direction,
                "stake": stake_val,
                "contract_id": contract_id,
                "strategy": "RiseFall",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )

        if TELEGRAM_ENABLED:
            try:
                await notifier.notify_trade_opened({
                    "contract_id": contract_id, "symbol": symbol,
                    "direction": direction, "stake": stake_val,
                    "entry_price": result.get("buy_price", 0),
                    "multiplier": 1, "duration": duration,
                    "duration_unit": duration_unit,
                    "payout": result.get("payout"),
                    "strategy_type": "RiseFall", "user_id": user_id,
                    "execution_reason": execution_reason,
                }, strategy_type="RiseFall")
            except Exception as e:
                logger.error(f"[RF] Telegram trade-open notification failed: {e}")

        logger.info(
            f"[RF] STEP 4/6 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"MONITORING #{contract_id} — system LOCKED"
        )
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "monitoring", "monitoring_trade",
            reason=f"Monitoring {symbol}#{contract_id} until 2-min settlement",
            details={"contract_id": contract_id, "direction": direction},
            min_interval_seconds=0,
        )

        settlement = await trade_engine.wait_for_result(contract_id, stake=stake_val)

        if settlement:
            pnl           = settlement["profit"]
            status        = settlement["status"]
            closure_reason = settlement.get("closure_type", "unknown")
            risk_manager.record_trade_closed(
                {
                    "contract_id": contract_id,
                    "profit": pnl,
                    "status": status,
                    "symbol": symbol,
                }
            )
        else:
            logger.warning(f"[RF][{symbol}] Settlement unknown for #{contract_id}")
            pnl           = -stake_val
            status        = "loss"
            closure_reason = "settlement_unknown"
            risk_manager.record_trade_closed(
                {
                    "contract_id": contract_id,
                    "profit": pnl,
                    "status": status,
                    "symbol": symbol,
                }
            )

        logger.info(
            f"[RF] CLOSING | contract={contract_id} status={status} "
            f"pnl={pnl:+.2f} closure={closure_reason}"
        )
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "closing", "closing_trade",
            reason=f"Closing {symbol}#{contract_id}: status={status}, pnl={pnl:+.2f}",
            details={"contract_id": contract_id, "status": status, "pnl": pnl},
            min_interval_seconds=0,
        )

        if user_id:
            db_write_success = await _write_trade_to_db_with_retry(
                user_id=user_id,
                contract_id=contract_id, symbol=symbol,
                direction=direction, stake_val=stake_val,
                pnl=pnl, status=status, closure_reason=closure_reason,
                duration=duration, duration_unit=duration_unit,
                result=result, settlement=settlement,
                UserTradesService=UserTradesService,
                zone_type=signal.get("zone_type"),
                zone_level=signal.get("zone_level"),
                confirmation_pattern=signal.get("confirmation_pattern"),
            )
        else:
            logger.warning(
                "[RF] No user_id - skipping DB write (trade lock will release)"
            )
            db_write_success = True

        if not db_write_success:
            risk_manager.halt(
                f"DB write failed for contract {contract_id} after "
                f"{rf_config.RF_DB_WRITE_MAX_RETRIES} retries"
            )
            await event_manager.broadcast(
                {
                    "type": "error",
                    "message": (
                        f"SYSTEM HALTED: DB write failed for {symbol}#{contract_id}. "
                        f"Trade lock held. Manual intervention required."
                    ),
                    "timestamp": datetime.now().isoformat(),
                    "account_id": user_id,
                }
            )
            return

        stats = risk_manager.get_statistics()
        try:
            fresh_balance = await data_fetcher.get_balance()
        except Exception:
            fresh_balance = None

        await event_manager.broadcast(
            {
                "type": "trade_closed",
                "symbol": symbol,
                "contract_id": contract_id,
                "pnl": pnl,
                "status": status,
                "strategy": "RiseFall",
                "closure_reason": closure_reason,
                "balance": fresh_balance,
                "active_positions": stats.get("active_positions", 0),
                "statistics": stats,
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        await event_manager.broadcast(
            {
                "type": "statistics",
                "stats": stats,
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        await event_manager.broadcast(
            {
                "type": "bot_status",
                "status": "running",
                "active_strategy": "RiseFall",
                "stake_amount": stake,
                "balance": fresh_balance,
                "active_positions": stats.get("active_positions", 0),
                "win_rate": stats.get("win_rate", 0),
                "trades_today": stats.get("trades_today", stats.get("total_trades", 0)),
                "profit": stats.get("total_pnl", 0),
                "pnl": stats.get("total_pnl", 0),
                "statistics": stats,
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "closing", "trade_closed",
            reason=f"{symbol} trade closed | P&L {pnl:+.2f}",
            details={"contract_id": contract_id, "status": status,
                     "pnl": pnl, "closure_reason": closure_reason},
            min_interval_seconds=0,
        )

        if TELEGRAM_ENABLED:
            try:
                result_info = {
                    "status": status,
                    "profit": pnl,
                    "contract_id": contract_id,
                    "current_price": (
                        settlement.get("sell_price", 0) if settlement else 0
                    ),
                    "duration": signal.get("duration", 0),
                    "exit_reason": closure_reason,
                    "strategy_type": "RiseFall",
                    "user_id": user_id,
                    "execution_reason": execution_reason,
                }
                await notifier.notify_trade_closed(
                    result_info,
                    {
                        "symbol": symbol,
                        "direction": direction,
                        "stake": stake_val,
                        "duration": signal.get("duration", 0),
                        "duration_unit": signal.get("duration_unit"),
                        "strategy_type": "RiseFall",
                        "user_id": user_id,
                        "execution_reason": execution_reason,
                        "closure_reason": closure_reason,
                    },
                    strategy_type="RiseFall",
                )
            except Exception as e:
                logger.error(f"[RF] Telegram trade-close notification failed: {e}")

        if closure_reason == "manual":
            await event_manager.broadcast(
                {
                    "type": "notification",
                    "level": "warning",
                    "title": "Manual Trade Close Detected",
                    "message": (
                        f"{symbol} contract #{contract_id} was manually closed on Deriv. "
                        f"Trade has been recorded in DB. P&L: ${pnl:.2f}"
                    ),
                    "timestamp": datetime.now().isoformat(),
                    "account_id": user_id,
                }
            )

        notification_type = "success" if pnl > 0 else "error" if pnl < 0 else "info"
        await event_manager.broadcast(
            {
                "type": "notification",
                "level": notification_type,
                "title": f"RF Trade {status.title()}",
                "message": f"{symbol} Rise/Fall trade closed. P&L: ${pnl:.2f}",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )

    except Exception as e:
        logger.error(f"[RF][{symbol}] Lifecycle error: {e}")
        await _broadcast_rf_decision(
            event_manager, user_id, symbol, "execution", "opportunity_failed",
            reason=f"Lifecycle error: {e}", severity="error", min_interval_seconds=0,
        )
        risk_manager.halt(f"Unexpected lifecycle error: {e}")
        await event_manager.broadcast(
            {
                "type": "error",
                "message": f"SYSTEM HALTED: Lifecycle error on {symbol}: {e}",
                "timestamp": datetime.now().isoformat(),
                "account_id": user_id,
            }
        )
        return

    finally:
        if risk_manager.is_halted():
            halt_reason = risk_manager._halt_reason
            halt_reason_lower = halt_reason.lower()
            is_transient = any(
                x in halt_reason_lower
                for x in [
                    "trade execution failed",
                    "lifecycle error",
                    "duplicate trade",
                ]
            )

            if is_transient:
                logger.warning(f"[RF] Transient halt — releasing lock. Reason: {halt_reason}")
                risk_manager.release_trade_lock(
                    reason=f"transient error recovery — {halt_reason}"
                )
                risk_manager.clear_halt()
                await event_manager.broadcast(
                    {
                        "type": "trade_lock_released",
                        "symbol": symbol,
                        "message": (
                            f"Trade lock released for transient error recovery on {symbol} "
                            f"(reason: {halt_reason})"
                        ),
                        "timestamp": datetime.now().isoformat(),
                        "account_id": user_id,
                    }
                )
                await _broadcast_rf_decision(
                    event_manager, user_id, symbol, "risk", "lock_released",
                    reason=f"Transient lock released: {halt_reason}",
                    min_interval_seconds=0,
                )
            else:
                logger.error(f"[RF] Critical halt — trade lock held. Reason: {halt_reason}")
                await _broadcast_rf_decision(
                    event_manager, user_id, symbol, "risk", "system_locked",
                    reason=f"System lock held: {halt_reason}",
                    severity="error", min_interval_seconds=0,
                )
                await event_manager.broadcast(
                    {
                        "type": "bot_status",
                        "status": "running",
                        "message": (
                            f"SYSTEM LOCKED: {halt_reason}. "
                            "Trade lock remains held until manual intervention."
                        ),
                        "timestamp": datetime.now().isoformat(),
                        "account_id": user_id,
                    }
                )
        else:
            await event_manager.broadcast(
                {
                    "type": "trade_lock_released",
                    "symbol": symbol,
                    "message": f"Trade UNLOCKED on {symbol} - scan resuming",
                    "timestamp": datetime.now().isoformat(),
                    "account_id": user_id,
                }
            )
            risk_manager.release_trade_lock(
                reason=f"{symbol} lifecycle complete — pnl={pnl:+.2f}"
            )


# ── DB write helper ──────────────────────────────────────────────────────────

async def _write_trade_to_db_with_retry(
    user_id: str,
    contract_id: str,
    symbol: str,
    direction: str,
    stake_val: float,
    pnl: float,
    status: str,
    closure_reason: str,
    duration: int,
    duration_unit: str,
    result: dict,
    settlement: dict,
    UserTradesService,
    zone_type: Optional[str] = None,
    zone_level: Optional[float] = None,
    confirmation_pattern: Optional[str] = None,
) -> bool:
    """
    Write trade to DB with configurable retries.

    Returns:
        True if DB write succeeded, False if all retries exhausted.
    """
    max_retries = rf_config.RF_DB_WRITE_MAX_RETRIES
    retry_delay = rf_config.RF_DB_WRITE_RETRY_DELAY

    duration_sec = 0
    if duration_unit == "m":
        duration_sec = int(duration * 60)
    elif duration_unit == "h":
        duration_sec = int(duration * 3600)
    elif duration_unit == "s":
        duration_sec = int(duration)

    trade_record = {
        "contract_id":          contract_id,
        "symbol":               symbol,
        "signal":               direction,
        "stake":                stake_val,
        "profit":               pnl,
        "status":               status,
        "duration":             duration_sec,
        "strategy_type":        "RiseFall",
        "closure_reason":       closure_reason,
        "timestamp":            datetime.now().isoformat(),
        "entry_price":          result.get("buy_price"),
        "exit_price":           settlement.get("sell_price") if settlement else None,
        # S&R-specific metadata
        "zone_type":            zone_type,
        "zone_level":           zone_level,
        "confirmation_pattern": confirmation_pattern,
    }

    for attempt in range(1, max_retries + 1):
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(
                f"[RF] STEP 5/6 | {ts} | DB write attempt {attempt}/{max_retries} "
                f"for contract {contract_id}"
            )
            saved = UserTradesService.save_trade(user_id, trade_record)
            if saved:
                logger.info(
                    f"[RF] STEP 5/6 | Trade persisted to DB: {contract_id} "
                    f"(attempt {attempt}/{max_retries})"
                )
                return True
            else:
                logger.error(
                    f"[RF] STEP 5/6 | DB write returned falsy for {contract_id} "
                    f"(attempt {attempt}/{max_retries})"
                )
        except Exception as e:
            logger.error(
                f"[RF] STEP 5/6 | DB write error for {contract_id} "
                f"(attempt {attempt}/{max_retries}): {e}"
            )
        if attempt < max_retries:
            logger.info(f"[RF] STEP 5/6 | Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)

    logger.critical(
        f"[RF] STEP 5/6 | ALL {max_retries} DB WRITE ATTEMPTS FAILED for {contract_id}"
    )
    return False