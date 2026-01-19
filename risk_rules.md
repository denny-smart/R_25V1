# Risk Management System Specification
*Status: Active | Last Updated: Phase 1 Completion*

This document serves as the single source of truth for the active risk management logic in the bot.

## 1. Global Portfolio Protection
These rules apply to the entire account to prevent catastrophic drawdowns.

| Rule | Value | Description |
| :--- | :--- | :--- |
| **Max Concurrent Trades** | **1** | System strictly locks after 1 valid trade. No new checks until it closes. |
| **Max Daily Loss** | **1.5x Stake** | Bot stops TRADING COMPLETELY if daily loss exceeds this amount (e.g., $150 on $100 stake). |
| **Consecutive Losses** | **2** | Bot goes into cooldown after 2 non-profitable trades in a row. |
| **Cooldown** | **3 Mins** | Mandatory waiting period between trades. |

## 2. Strict Entry Gatekeepers
Every signal must pass ALL these checks to be executed. If one fails, the trade is **REJECTED**.

### A. Risk Requirements
*   **Max Risk Per Trade:** **15.0%** of Stake.
    *   *Calculation:* `(StopPrice - Entry) / Entry * Multiplier * Stake` must be < 15% of Stake.
*   **Min Risk:Reward (R:R):** **1:2.5**.
    *   *Requirement:* Potential Profit must be at least 2.5x the Potential Risk.

### B. Quality Requirements
*   **Min Signal Strength:** **8.0** / 10.0.
*   **Market Structure:** Entry works on "Breakout + Weak Retest" logic only.

## 3. Dynamic Trade Management (Exits)

### A. Fast Failure (Early Exit)
Disconnects "heavy" losers quickly before they hit full Stop Loss.
*   **Condition:** Loss > **5.0%** of Stake.
    *   *Time Window:*
        *   **Day Mode (Standard):** First **45 seconds**.
        *   **Night Mode (Volatile):** First **20 seconds**.

### B. Stagnation Kill
Frees up capital if price is going nowhere.
*   **Condition:** Trade still in a loss (> 6% of stake) after **90 seconds**.
*   **Action:** Immediate Close.

### C. Price-Based Trailing Stop (Tiered)
*Breakeven Protection is **DISABLED**.*
We use a **"Lock & Trail"** system using a price-distance formula.

**Formula:**
1.  **Risk($)** = `Stake * Trail %`
2.  **Distance** = `(Risk($) * EntryPrice) / (Multiplier * Stake)`
3.  **Stop Price** = `Current Price` +/- `Distance`

**Active Tiers:**

| Tier Name | Trigger (Profit %) | Trail % (Risk $) | Logic |
| :--- | :--- | :--- | :--- |
| **Initial Lock** | **+8%** | **4%** | Locks tight ($4 risk gap) once profit hits $8. |
| **Profit Secured** | **+15%** | **6%** | Widens slightly to let trade breathe. |
| **Big Winner** | **+25%** | **8%** | Trails loosely for swing potential. |
| **Excellent** | **+50%** | **15%** | Wide trail for moonshots. |

*Note: The Stop Price ONLY moves in the profitable direction. It never loosens.*
