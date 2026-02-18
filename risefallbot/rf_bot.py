"""
Rise/Fall Bot Orchestrator
Main async loop — subscribes to 1-min OHLC, generates signals, executes trades
rf_bot.py
"""

import asyncio
import os
import logging
from datetime import datetime
from typing import Optional

from data_fetcher import DataFetcher
from risefallbot import rf_config
from risefallbot.rf_strategy import RiseFallStrategy
from risefallbot.rf_risk_manager import RiseFallRiskManager
from risefallbot.rf_trade_engine import RFTradeEngine

# Dedicated logger for Rise/Fall bot orchestration — writes to its own file
logger = logging.getLogger("risefallbot")

# Module-level sentinel for clean stop
_running = False
_current_task: Optional[asyncio.Task] = None


def _setup_rf_logger():
    """
    Configure the risefallbot logger hierarchy so all RF modules
    (risefallbot.strategy, risefallbot.risk, risefallbot.engine)
    write ONLY to risefall_bot.log and do NOT propagate to the root
    (multiplier bot) logger.
    """
    rf_root = logging.getLogger("risefallbot")

    # Prevent double-handler on re-import
    if rf_root.handlers:
        return

    rf_root.setLevel(getattr(logging, rf_config.RF_LOG_LEVEL, logging.INFO))
    rf_root.propagate = False  # ← isolate from multiplier bot logs

    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    fh = logging.FileHandler(rf_config.RF_LOG_FILE, encoding="utf-8")
    fh.setFormatter(formatter)
    rf_root.addHandler(fh)

    # Console handler (optional — useful during development)
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    rf_root.addHandler(ch)


# Initialise logging on module load
_setup_rf_logger()


async def _fetch_user_config() -> dict:
    """
    Fetch deriv_api_key and stake_amount from Supabase profiles table
    for the first user who has active_strategy = 'RiseFall'.
    Falls back to env-var token and config default stake.
    """
    result_config = {
        "api_token": os.getenv("DERIV_API_TOKEN"),
        "stake": rf_config.RF_DEFAULT_STAKE,
    }

    try:
        from app.core.supabase import supabase
        result = (
            supabase.table("profiles")
            .select("deriv_api_key, stake_amount")
            .eq("active_strategy", "RiseFall")
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            if row.get("deriv_api_key"):
                result_config["api_token"] = row["deriv_api_key"]
                logger.info("🔑 API token loaded from user profile")
            if row.get("stake_amount") is not None:
                result_config["stake"] = float(row["stake_amount"])
                logger.info(f"💵 User stake loaded from profile: ${result_config['stake']}")
    except Exception as e:
        logger.warning(f"⚠️ Could not fetch user config from Supabase: {e}")

    return result_config


async def run(stake: Optional[float] = None, api_token: Optional[str] = None):
    """
    Main Rise/Fall bot entry point.
    
    Args:
        stake: User stake amount. If None, fetches from Supabase profiles table.
        api_token: Deriv API token. If None, fetches from Supabase profiles table.
    
    - Creates its own DataFetcher (reuses the class, own WS connection)
    - Creates its own RFTradeEngine (independent WS connection)
    - Loops: fetch 1m candles → analyse → risk check → execute
    """
    logger.info("=" * 60)
    logger.info("🚀 Rise/Fall Scalping Bot Starting")
    logger.info("=" * 60)

    # Resolve user config: explicit params > Supabase profile > env vars
    user_cfg = await _fetch_user_config()
    if stake is None:
        stake = user_cfg["stake"]
    if api_token is None:
        api_token = user_cfg["api_token"]

    if not api_token:
        logger.error("❌ No API token found (profile or DERIV_API_TOKEN env) — cannot start Rise/Fall bot")
        return

    # --- Instantiate components ---
    strategy = RiseFallStrategy()
    risk_manager = RiseFallRiskManager()
    data_fetcher = DataFetcher(api_token, rf_config.RF_APP_ID)
    trade_engine = RFTradeEngine(api_token, rf_config.RF_APP_ID)

    # --- Connect ---
    if not await data_fetcher.connect():
        logger.error("❌ DataFetcher connection failed — aborting")
        return
    if not await trade_engine.connect():
        logger.error("❌ RFTradeEngine connection failed — aborting")
        await data_fetcher.disconnect()
        return

    logger.info(f"📊 Symbols: {rf_config.RF_SYMBOLS}")
    logger.info(f"⏱️ Scan interval: {rf_config.RF_SCAN_INTERVAL}s")
    logger.info(f"💵 Stake: ${stake}")
    logger.info(f"📏 Contract: {rf_config.RF_CONTRACT_DURATION}{rf_config.RF_DURATION_UNIT}")
    logger.info("=" * 60)

    global _running
    _running = True
    cycle = 0

    try:
        while _running:
            cycle += 1
            logger.info(
                f"\n{'='*50}\n"
                f"[RF] CYCLE #{cycle} | {datetime.now().strftime('%H:%M:%S')}\n"
                f"{'='*50}"
            )

            for symbol in rf_config.RF_SYMBOLS:
                try:
                    await _process_symbol(
                        symbol, strategy, risk_manager, data_fetcher, trade_engine, stake
                    )
                except Exception as e:
                    logger.error(f"[RF][{symbol}] ❌ Error: {e}")

            # Log summary
            stats = risk_manager.get_statistics()
            logger.info(
                f"[RF] Cycle #{cycle} done | "
                f"trades={stats['trades_today']} "
                f"W={stats['wins']} L={stats['losses']} "
                f"pnl={stats['total_pnl']:+.2f}"
            )

            await asyncio.sleep(rf_config.RF_SCAN_INTERVAL)

    except asyncio.CancelledError:
        logger.info("🛑 Rise/Fall bot cancelled")
    except Exception as e:
        logger.error(f"❌ Rise/Fall bot fatal error: {e}")
    finally:
        _running = False
        await data_fetcher.disconnect()
        await trade_engine.disconnect()
        logger.info("🛑 Rise/Fall bot stopped")


def stop():
    """Signal the Rise/Fall bot loop to stop."""
    global _running
    _running = False
    logger.info("🛑 Rise/Fall bot stop requested")


async def _process_symbol(
    symbol: str,
    strategy: RiseFallStrategy,
    risk_manager: RiseFallRiskManager,
    data_fetcher: DataFetcher,
    trade_engine: RFTradeEngine,
    stake: float,
):
    """
    Process one symbol: fetch data → analyse → risk check → trade.
    """
    # 1. Risk gate (per-symbol)
    can_trade, reason = risk_manager.can_trade(symbol=symbol)
    if not can_trade:
        logger.debug(f"[RF][{symbol}] ⏸️ {reason}")
        return

    # 2. Fetch 1-minute candle data (reuse DataFetcher)
    df = await data_fetcher.fetch_timeframe(
        symbol, rf_config.RF_TIMEFRAME, count=rf_config.RF_CANDLE_COUNT
    )
    if df is None or df.empty:
        logger.warning(f"[RF][{symbol}] No data returned")
        return

    # 3. Strategy analysis
    signal = strategy.analyze(data_1m=df, symbol=symbol, stake=stake)
    if signal is None:
        return  # No triple-confirmation — already logged by strategy

    # 4. Execute trade
    direction = signal["direction"]
    stake = signal["stake"]
    duration = signal["duration"]
    duration_unit = signal["duration_unit"]

    result = await trade_engine.buy_rise_fall(
        symbol=symbol,
        direction=direction,
        stake=stake,
        duration=duration,
        duration_unit=duration_unit,
    )

    if not result:
        logger.error(f"[RF][{symbol}] Trade execution failed")
        return

    contract_id = result["contract_id"]

    # 5. Record trade open
    risk_manager.record_trade_open({
        "contract_id": contract_id,
        "symbol": symbol,
        "direction": direction,
        "stake": stake,
    })

    # 6. Wait for contract settlement (async — blocks only this symbol)
    settlement = await trade_engine.wait_for_result(contract_id)

    if settlement:
        risk_manager.record_trade_closed({
            "contract_id": contract_id,
            "profit": settlement["profit"],
            "status": settlement["status"],
            "symbol": symbol,
        })
    else:
        # Settlement unknown — conservatively mark as loss
        logger.warning(f"[RF][{symbol}] ⚠️ Settlement unknown for #{contract_id}")
        risk_manager.record_trade_closed({
            "contract_id": contract_id,
            "profit": -stake,
            "status": "loss",
            "symbol": symbol,
        })
