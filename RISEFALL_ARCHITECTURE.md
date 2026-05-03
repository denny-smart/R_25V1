# RiseFall Strategy Architecture

This document gives a simple but complete view of how the RiseFall strategy works in this codebase.

## 1. High-Level Picture

```text
Client/API
   |
   v
app.bot.manager.BotManager
   |
   v
risefallbot.rf_bot.run(user_id, api_token, stake)
   |
   +--> DataFetcher            -> fetches 1m OHLC candles from Deriv
   +--> RiseFallStrategy       -> decides whether a CALL/PUT setup exists
   +--> RiseFallRiskManager    -> blocks unsafe trades and enforces 1-trade lifecycle
   +--> RFTradeEngine          -> buys and monitors Rise/Fall contracts on Deriv
   +--> Event Manager          -> pushes bot status / signals / trade events to frontend
   +--> Trades Service         -> writes finished trades to the database
   +--> Telegram / Logging     -> notifications and audit trail
```

## 2. Main Components

### Entry and orchestration

- `app/bot/manager.py`
  - Starts RiseFall as its own asyncio task.
  - Keeps one task per user in memory.
  - Applies graceful stop/restart.
  - Uses a Supabase session lock to prevent duplicate bot instances across processes.

- `risefallbot/rf_bot.py`
  - Main orchestrator for the RiseFall bot.
  - Builds the runtime objects.
  - Runs the scan loop.
  - Coordinates the strict 6-step trade lifecycle.
  - Broadcasts UI events and writes logs.

### Market data and execution

- `data_fetcher.py`
  - Opens a Deriv WebSocket connection for market data.
  - Fetches 1-minute candles for each configured symbol.

- `risefallbot/rf_trade_engine.py`
  - Opens a separate Deriv WebSocket connection for trading.
  - Sends buy requests for `CALL` and `PUT`.
  - Watches the open contract until expiry or manual close.
  - Includes ghost-contract recovery and stale-message protection.

### Decision engine

- `risefallbot/rf_strategy.py`
  - Evaluates Step Index tick-sequence reversals.
  - Produces a signal dict or rejects the setup with a reason code.

### Risk and state

- `risefallbot/rf_risk_manager.py`
  - Enforces the real trading guardrails.
  - Owns the async trade mutex.
  - Tracks active trade, cooldowns, daily stats, streaks, and halted state.

- `risefallbot/rf_config.py`
  - Holds strategy parameters, symbol universe, risk limits, timeouts, and feature flags.

## 3. Runtime Flow

### A. Bot startup

```text
BotManager.start_bot(...)
   -> resolve strategy = RiseFall
   -> _start_risefall_bot(...)
   -> acquire cross-process DB session lock
   -> create asyncio task for rf_bot.run(...)
```

`rf_bot.run(...)` then:

```text
1. Loads user config
2. Instantiates:
   - RiseFallStrategy
   - RiseFallRiskManager
   - DataFetcher
   - RFTradeEngine
3. Connects both WebSocket clients
4. Broadcasts bot_status=running and initial statistics
5. Enters the scan loop
```

### B. Scan loop

For every cycle:

```text
1. Refresh session lock
2. Reset daily stats at midnight if needed
3. Run watchdog recovery checks
4. If halted -> do not scan
5. If trade lifecycle is active -> do not scan
6. Otherwise iterate configured symbols and call _process_symbol(...)
```

### C. Per-symbol processing

`_process_symbol(...)` does this:

```text
1. Risk pre-check with can_trade(symbol, stake)
2. Fetch latest 1m candles
3. Run strategy.analyze(...)
4. If no setup -> emit structured skip reason
5. If setup exists -> validate stake cap
6. Acquire trade mutex without waiting
7. Execute Deriv buy request
8. Record trade open in risk manager
9. Monitor contract until settlement
10. Record trade close in risk manager
11. Write trade to DB with retry
12. Broadcast close/unlock events
13. Release lock and resume scanning
```

## 4. Strategy Logic

The RiseFall strategy is a layered decision pipeline.

### Core entry logic

Base signal in `rf_strategy.py`:

- `CALL`
  - `EMA_fast > EMA_slow`
  - `RSI < oversold`
  - `Stochastic %K < oversold`

- `PUT`
  - `EMA_fast < EMA_slow`
  - `RSI > overbought`
  - `Stochastic %K > overbought`

### Optional structural filters

Enabled from `rf_config.py`:

- Zone filter
  - Price must be near a detected support/resistance/middle zone.

- Market bias filter
  - Rejects `CALL` against bearish bias.
  - Rejects `PUT` against bullish bias.

- Momentum candle filter
  - Requires strong candle body, controlled wick, and body strength above recent average.

- Candle direction alignment
  - `CALL` requires bullish candle.
  - `PUT` requires bearish candle.

- Scenario classifier
  - Labels setup as `breakout`, `retest`, or `basic`.
  - `basic` can be allowed or blocked via config.

### Signal output

If accepted, strategy returns:

```text
{
  symbol,
  direction,
  stake,
  duration,
  duration_unit,
  rsi,
  stoch,
  market_bias,
  scenario,
  zone_type,
  zone_level,
  confidence
}
```

If rejected, it stores a structured reason such as:

- `warmup_insufficient_bars`
- `zone_miss`
- `candle_quality_fail`
- `triple_confirmation_fail`
- `bias_mismatch`
- `basic_scenario_filtered`

## 5. Risk Architecture

The real safety model is centered on `RiseFallRiskManager`.

### Core rule

Only one trade lifecycle is allowed at a time for a given bot instance.

This is enforced by:

- `asyncio.Lock` trade mutex
- `active_trades` tracking
- per-symbol and global cooldown checks
- halted-state checks
- post-acquire race checks

### Risk checks in `can_trade(...)`

- system not halted
- trade mutex not already held
- daily trade cap not reached
- daily loss limit not exceeded
- loss-streak cooldown not active
- total concurrent trades below max
- global cooldown passed
- symbol not blocked
- per-symbol concurrent count below max
- per-symbol cooldown passed

### Trade lifecycle control

```text
Step 1: acquire_trade_lock(...)
Step 2: execute trade via RFTradeEngine.buy_rise_fall(...)
Step 3: record_trade_open(...)
Step 4: wait_for_result(...) and record_trade_closed(...)
Step 5: write trade to DB
Step 6: release lock
```

Important detail:

- The lock is intentionally kept until the DB write succeeds.
- If a critical failure happens, the system can halt instead of silently continuing.

## 6. Execution Architecture

`RFTradeEngine` is isolated from the multiplier trade engine used by other strategies.

### Why it is separate

- RiseFall uses Deriv Rise/Fall contracts, not multiplier positions.
- It needs its own connection and contract-monitoring logic.

### Buy flow

```text
buy_rise_fall(...)
   -> validate symbol and direction
   -> ensure trade WS is connected
   -> send buy request
   -> on success return contract details
   -> on failure check for ghost contract before returning None
```

### Settlement flow

```text
wait_for_result(contract_id)
   -> flush stale WS messages
   -> subscribe to proposal_open_contract
   -> discard unrelated contract updates
   -> wait until sold/expired
   -> return profit, status, sell_price, closure_type
```

### Safety hardening in the engine

- Ghost contract detection
  - Recovers when Deriv opens the contract but the buy response is lost.

- Stale message flushing and contract-id validation
  - Prevents previous contract updates from being misread as the current contract result.

## 7. Data, State, and Persistence

### Live runtime state

Held mostly in `rf_bot.py` and `rf_risk_manager.py`:

- running state per user
- task per user
- active trade info
- daily PnL and trade count
- win/loss counters
- consecutive losses
- cooldown timestamps
- halted reason and timestamp

### Persistent state

- User profile/config is loaded from Supabase.
- Completed trades are written through `UserTradesService`.
- Session lock rows prevent duplicate RiseFall instances across processes.

## 8. Observability

The RiseFall strategy is designed to be visible to both operators and UI clients.

### Broadcast events

`rf_bot.py` emits events such as:

- `bot_status`
- `statistics`
- `signal`
- `trade_opened`
- `trade_closed`
- `trade_lock_active`
- `notification`
- structured decision events for scan/risk/signal/execution/monitoring/closing

### Logging

- Dedicated logger namespace: `risefallbot`
- Per-user log files under `logs/risefall/`
- Separate child loggers for:
  - strategy
  - risk
  - engine

## 9. Configuration Summary

Main config groups in `rf_config.py`:

- symbol universe
- candle timeframe and count
- indicator thresholds
- zone and candle filter tuning
- contract duration and stake defaults
- risk limits and cooldowns
- WebSocket settings
- DB write retry settings
- graceful shutdown timeout

## 10. Recommended Mental Model

Think of RiseFall as 4 layers:

```text
Layer 1: Orchestration
  BotManager + rf_bot

Layer 2: Decision
  rf_strategy

Layer 3: Safety
  rf_risk_manager

Layer 4: Market I/O
  DataFetcher + RFTradeEngine + DB/event integrations
```

And one simple rule governs everything:

```text
No new signal may become a live trade unless:
1. strategy says the setup is valid,
2. risk manager says trading is allowed,
3. the trade mutex is acquired,
4. the previous trade lifecycle is fully closed and persisted.
```
