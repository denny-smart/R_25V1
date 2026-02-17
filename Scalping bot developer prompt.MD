# Developer Implementation Brief
## R50BOT v3.1 — Scalping Bot Extension
**Project:** R50BOT Multi-Asset Trading System  
**Task:** Add a Scalping Bot Strategy alongside the existing Conservative Bot  
**Priority:** High  
**Constraint:** The existing conservative bot must not be modified in any way

---

## Background

The existing system (R50BOT v3.0) is a FastAPI-based automated trading bot that connects
to the Deriv API. It currently runs a single conservative top-down multi-timeframe strategy
with 29 validation checks before executing any trade. Because the rules are strict, the bot
sometimes goes days or weeks without executing a trade.

The goal of this task is to add a second bot strategy — a **Scalping Bot** — that trades more
frequently using relaxed rules, while still applying proper risk management. The two strategies
must be completely independent of each other, sharing only the execution infrastructure.

You will be working across the following existing files:

- `strategy.py` — Current conservative strategy (DO NOT MODIFY)
- `risk_manager.py` — Current risk manager (DO NOT MODIFY)
- `trade_engine.py` — Trade execution engine (DO NOT MODIFY)
- `app/bot/runner.py` — Per-user bot runner
- `app/bot/manager.py` — Multi-user bot orchestrator
- `app/api/config.py` — Configuration API routes
- `app/api/bot.py` — Bot control API routes
- `config.py` — Trading configuration constants
- `supabase_setup.sql` — Database schema

---

## Strict Rules Before You Begin

1. **Do NOT modify** `strategy.py`, `risk_manager.py`, or `trade_engine.py` under any circumstances.
2. **Do NOT change** any existing database columns — only add new ones.
3. **Do NOT alter** any existing API endpoint signatures — only add new ones.
4. All new logic must live in **new files** wherever possible.
5. The conservative bot must behave identically to how it does today after your changes are merged.

---

## Task 1 — Create a Strategy Abstraction Layer

Create a new file: `base_strategy.py`

This file must define an abstract base class (interface) that both the conservative and scalping
strategies will implement. The interface must define the following methods:

- `analyze(data)` — returns a signal dict (with direction, TP, SL, RR ratio, confidence) or None
- `get_required_timeframes()` — returns a list of timeframe strings the strategy needs
- `get_strategy_name()` — returns the strategy identifier string

Do not put any logic in this base class — it is purely a contract.

---

## Task 2 — Create a Risk Manager Abstraction Layer

Create a new file: `base_risk_manager.py`

This file must define an abstract base class that both the conservative and scalping risk
managers will implement. The interface must define:

- `can_trade()` — returns True or False
- `record_trade_opened(trade)` — updates internal counters
- `record_trade_closed(result)` — updates win/loss counters and P&L
- `get_current_limits()` — returns a dict of all active thresholds for status reporting
- `reset_daily_stats()` — resets counters at midnight

---

## Task 3 — Wrap the Existing Conservative Strategy

Create a new file: `conservative_strategy.py`

This file must import the existing `strategy.py` logic and wrap it in a class that implements
the `base_strategy.py` interface. Do not copy code from `strategy.py` — import and delegate to it.
The strategy name returned by `get_strategy_name()` must be "Conservative".

Create a new file: `conservative_risk_manager.py`

Same approach — wrap the existing `risk_manager.py` in a class implementing `base_risk_manager.py`.
Import and delegate. Do not duplicate code.

This wrapping step ensures the existing logic is untouched while making it compatible with
the new factory system.

---

## Task 4 — Build the Scalping Strategy

Create a new file: `scalping_strategy.py`

This class must implement `base_strategy.py`. It performs its own independent market analysis
using only three timeframes: 1h, 5m, and 1m. It must never reference or import `strategy.py`.

### Validation Rules (implement all of the following):

| Check | Rule |
|---|---|
| Timeframes required | 1h, 5m, 1m only |
| Trend alignment | 1h and 5m must both be BULLISH or both BEARISH |
| ADX threshold | ADX >= 18 |
| RSI range for UP signal | RSI between 52 and 80 |
| RSI range for DOWN signal | RSI between 20 and 48 |
| Price movement filter (R_50) | Reject if price already moved > 1.2% |
| Momentum breakout | Recent candle must exceed 1.2x ATR |
| Parabolic spike detection | Same logic as conservative — retain this check unchanged |
| TP/SL method | Primary: ATR-based (SL = 1.5x ATR, TP = 2.25x ATR). Override with structure level if one exists within that range |
| Minimum R:R ratio | 1.5 |
| Indicator fallback | RSI=50, ADX=0 on calculation failure (ADX=0 safely blocks all trades) |

The `analyze()` method must return None with a logged reason for every failed check, using
the same logging pattern as the existing strategy.

---

## Task 5 — Build the Scalping Risk Manager

Create a new file: `scalping_risk_manager.py`

This class must implement `base_risk_manager.py` with the following independent thresholds.
It must manage its own state — it must NOT share state with the conservative risk manager.

### Risk Parameters:

| Parameter | Value |
|---|---|
| Max concurrent trades | 4 |
| Cooldown between trades | 30 seconds |
| Max trades per day | 80 |
| Max consecutive losses | 4 |
| Daily loss limit | 2x user stake |
| Circuit breaker | Halt after 4 consecutive losses |
| Daily stats reset | Midnight, same as conservative |

### Important — Daily Counter Inheritance:

When the scalping bot starts, it must load the current day's trade count and P&L from the
database (not from memory) so that switching strategies mid-day does not reset these counters.
A user cannot escape daily limits by switching strategies.

### Runaway Trade Guardrail:

Inside the scalping risk manager, add a check: if more than 10 trades have been opened within
any rolling 10-minute window for this user, call `can_trade()` returning False and emit a warning
log. This is a safety net for bugs, not a strategy rule.

---

## Task 6 — Create the Strategy Registry

Create a new file: `strategy_registry.py`

This file contains a single dictionary mapping strategy name strings to their implementation
class pairs. The registry maps:

- "Conservative" to (ConservativeStrategy class, ConservativeRiskManager class)
- "Scalping" to (ScalpingStrategy class, ScalpingRiskManager class)

Add a lookup function that accepts a strategy name string and returns the correct class pair.
If the name is not found in the registry, it must log a warning and return the Conservative pair
as a safe default. It must never raise an exception or return None.

---

## Task 7 — Update the Bot Runner

Modify `app/bot/runner.py` to accept injected strategy and risk manager instances rather than
instantiating them internally.

The `BotRunner.__init__()` method must accept two new parameters:
- `strategy` — an instance implementing `base_strategy.py`
- `risk_manager` — an instance implementing `base_risk_manager.py`

Replace all internal references to the hardcoded strategy and risk manager with these injected
instances. The trading loop itself (`trading_cycle()`) must not change in structure — it simply
calls `self.strategy.analyze()` and `self.risk_manager.can_trade()` as before.

Add one new behaviour: when saving a trade to the database, include the `strategy_type` field
(read from `self.strategy.get_strategy_name()`).

---

## Task 8 — Update the Bot Manager

Modify `app/bot/manager.py` to perform strategy injection at bot startup.

When `start_bot(user_id)` is called:

1. Read the user's `active_strategy` value from their profile in Supabase.
2. Look up the corresponding class pair in the strategy registry.
3. Read any user-specific overrides from the `strategy_configs` table (see Task 10).
4. Instantiate the strategy and risk manager with the correct configuration.
5. Pass these instances into `BotRunner`.

### Strategy Switch Handling:

If a user's bot is already running and they start a new one with a different strategy:
- Do NOT spin up a second instance.
- Stop the existing instance cleanly (allow open trades to finish monitoring).
- Start a fresh instance with the new strategy.
- Log this transition clearly.

### Concurrent Start Request Protection:

If two start requests arrive simultaneously for the same user, the second must return a
409 Conflict response. Use a per-user asyncio lock or equivalent mechanism. The lock must
be released whether the start succeeds or fails.

---

## Task 9 — Database Migrations

Make the following changes to the database schema. Add these to `supabase_setup.sql` as
additive migrations (never drop or alter existing columns):

### 9.1 — bot_trades table

Add column: `strategy_type TEXT NOT NULL DEFAULT 'Conservative'`

Add a check constraint: value must be one of 'Conservative' or 'Scalping'.

Write a one-time backfill migration that sets `strategy_type = 'Conservative'` for all
existing rows where strategy_type is null.

### 9.2 — profiles table

The existing `active_strategy` column stays as-is. Add a check constraint to it enforcing
that values must be either 'Conservative' or 'Scalping'. If any existing rows have other
values, the backfill migration must set them to 'Conservative'.

### 9.3 — New table: strategy_configs

Create a new table with the following columns:

- `id` — uuid, primary key
- `user_id` — uuid, foreign key to auth.users, unique
- `strategy_type` — text, check constraint ('Conservative' or 'Scalping')
- `max_concurrent_trades` — integer, nullable
- `cooldown_seconds` — integer, nullable
- `max_trades_per_day` — integer, nullable
- `max_consecutive_losses` — integer, nullable
- `daily_loss_multiplier` — numeric, nullable
- `custom_params` — jsonb, nullable (for strategy-specific thresholds)
- `updated_at` — timestamp with time zone

Apply RLS policies: users can read and write only their own row.

---

## Task 10 — New and Updated API Endpoints

### 10.1 — New: Strategy Selection

`PUT /api/v1/config/strategy`

Request body: `{ "strategy": "Conservative" | "Scalping" }`

- Validate that the value is one of the two allowed strings.
- Write to `active_strategy` on the user's profile.
- Return the updated profile object.
- Do NOT restart any running bot — the change takes effect on next bot start.
- If `SCALPING_BOT_ENABLED` environment variable is false, reject "Scalping" with a
  403 Forbidden and message: "Scalping bot is not currently enabled."

### 10.2 — New: Strategy Parameters

`GET /api/v1/config/strategy-params`

Returns the **effective** configuration for the user's active strategy — that is, the system
defaults merged with any user overrides from `strategy_configs`. Never return just the raw
override row; always merge with defaults so the frontend sees complete values.

`PUT /api/v1/config/strategy-params`

Accepts a partial object of overrideable parameters. Write to `strategy_configs`. Validate
that numeric values are within safe bounds (e.g., max_concurrent_trades cannot exceed 6,
cooldown cannot be below 10 seconds).

### 10.3 — Update: Bot Status

Extend the response of `GET /api/v1/bot/status` to include:

- `active_strategy` — the strategy name currently running
- `effective_limits` — the key risk parameters in effect (from `risk_manager.get_current_limits()`)

### 10.4 — Update: Trade History

Extend `GET /api/v1/trades` to accept an optional query parameter: `?strategy_type=Conservative`
or `?strategy_type=Scalping`. When provided, filter results by that strategy type.

---

## Task 11 — Environment Variable

Add a new environment variable: `SCALPING_BOT_ENABLED`

- Type: boolean (true / false)
- Default: false
- Add it to `.env.example` with a comment explaining its purpose.
- When false, the strategy selection endpoint rejects "Scalping", and the registry lookup
  for "Scalping" must also fall back to Conservative with a warning log.

---

## Edge Cases You Must Handle

### Open Trades on Strategy Switch
When a user switches strategy and restarts, any trades opened under the previous strategy must
continue to be monitored by the trade engine until they close. The trade engine is
strategy-agnostic — this should work automatically. Confirm it does.

### Daily Counter Inheritance
On bot startup, the risk manager must query the database for today's trade count and P&L
and seed its internal counters accordingly. Do not start counters at zero if trades already
happened today under a different strategy session.

### Concurrent Slot Count on Restart
On bot startup, the risk manager must query the database for currently open trades and seed
the concurrent trade slot counter from that count — not from zero.

### Strategy Registry Unknown Value
If `active_strategy` from the database does not match any registry key, log a warning,
default to Conservative, and include a flag in the bot status response indicating that a
fallback occurred.

### Indicator Calculation Failure (Scalping)
Same safe fallback as conservative: RSI=50, ADX=0. Since ADX=0 is below the scalping
threshold of 18, all trades are safely blocked without additional handling.

---

## Testing Requirements

Before marking this task complete, verify the following:

- [ ] Starting the conservative bot behaves identically to before this change
- [ ] Starting the scalping bot uses the correct thresholds (confirm via logs)
- [ ] Switching strategy mid-session stops the old bot and starts the new one cleanly
- [ ] A second concurrent start request for the same user returns 409
- [ ] Daily counters persist correctly across a strategy switch
- [ ] The `strategy_type` column is written correctly on every new trade
- [ ] `GET /api/v1/trades?strategy_type=Scalping` returns only scalping trades
- [ ] `SCALPING_BOT_ENABLED=false` blocks scalping selection at the API level
- [ ] Bot status response includes `active_strategy` and `effective_limits`
- [ ] Unknown `active_strategy` database value falls back to Conservative without crashing
- [ ] The runaway trade guardrail (10 trades in 10 minutes) triggers `can_trade()` returning False

---

## Deliverables

When complete, the following new files must exist:

- `base_strategy.py`
- `base_risk_manager.py`
- `conservative_strategy.py`
- `conservative_risk_manager.py`
- `scalping_strategy.py`
- `scalping_risk_manager.py`
- `strategy_registry.py`

The following existing files will have been modified:

- `app/bot/runner.py` — strategy injection
- `app/bot/manager.py` — strategy lookup and injection at startup
- `app/api/config.py` — new strategy endpoints
- `app/api/bot.py` — extended status response
- `supabase_setup.sql` — new columns, new table, backfill migrations
- `.env.example` — new environment variable
- `config.py` — scalping default constants added (conservative constants untouched)

---

## Questions Before Starting

If anything in this brief is unclear, ask before writing any code. The most likely points of
confusion are:

1. How daily counter inheritance should behave when a user has run zero trades today
   (answer: seed at zero — no database query needed, but the query must handle empty results gracefully)

2. Whether the scalping bot should support all 7 assets or a subset
   (answer: all 7 assets, using the same asset-specific movement thresholds scaled proportionally
   from the conservative values — multiply each by 1.7x as a starting point)

3. Whether user-overrideable params should have hard maximums enforced server-side
   (answer: yes — enforce in the API handler, not in the strategy class)

---

*Brief prepared: 2026-02-17 | System version target: R50BOT v3.1*