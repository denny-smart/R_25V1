
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config

# Mock config to simulate the mismatch
# Config has fixed low percentages
config.TAKE_PROFIT_PERCENT = 0.24
config.STOP_LOSS_PERCENT = 0.0413
config.FIXED_STAKE = 10.0
config.MULTIPLIER = 100

from telegram_notifier import TelegramNotifier

async def verify():
    print("--- Verifying Telegram Notification Logic ---")
    
    notifier = TelegramNotifier()
    # Mock send_message to capture the output
    notifier.send_message = MagicMock(return_value=asyncio.Future())
    notifier.send_message.return_value.set_result(True)
    notifier.enabled = True
    
    # Simulate a trade with Dynamic TP/SL (Top-Down)
    # Entry: 100
    # TP: 101 (1% move) -> With 100x multiplier, this is 100% profit
    # SL: 99 (1% move) -> With 100x multiplier, this is 100% loss
    
    # Expected amounts:
    # Stake: 10
    # Profit: 10 * 100 * (1/100) = 10.0
    # Loss: 10 * 100 * (1/100) = 10.0
    
    # Current Buggy Behavior:
    # Uses config.TAKE_PROFIT_PERCENT (0.24%)
    # Profit: 10 * 100 * (0.0024) = 2.4
    
    trade_info = {
        'symbol': 'TEST_SYMBOL',
        'direction': 'BUY',
        'stake': 10.0,
        'multiplier': 100,
        'entry_price': 10.0, # Stake
        'entry_spot': 100.0, # Market Price
        # Dynamic TP/SL
        'take_profit': 101.0, 
        'stop_loss': 99.0,
        'contract_id': '12345'
    }
    
    print("\n[Test Case]")
    print(f"Stake: ${trade_info['stake']}")
    print(f"Multiplier: x{trade_info['multiplier']}")
    print(f"Entry Spot: {trade_info['entry_spot']}")
    print(f"TP Price: {trade_info['take_profit']} (Diff: +1.0)")
    print(f"SL Price: {trade_info['stop_loss']} (Diff: -1.0)")
    print(f"Config TP %: {config.TAKE_PROFIT_PERCENT}%")
    
    expected_profit = 10.0 # 100% ROI
    current_buggy_profit = 2.4 # 24% ROI (0.24 * 100)
    
    await notifier.notify_trade_opened(trade_info)
    
    # Extract message
    call_args = notifier.send_message.call_args
    if call_args:
        message = call_args[0][0] # First arg is message
        print("\n[Generated Message Content]")
        print(message)
        
        # Check for values
        if "$10.00" in message and "Target: +$10.00" in message:
             print("\n✅ PASS: Calculated based on dynamic prices.")
        elif "Target: +$2.40" in message:
             print("\n❌ FAIL: Calculated based on fixed config (BUG REPRODUCED).")
        else:
             print("\n⚠️ INDETERMINATE: Check message content manually.")
             
    else:
        print("❌ Error: send_message was not called.")

if __name__ == "__main__":
    asyncio.run(verify())
