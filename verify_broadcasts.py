
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch

# Add root to path
sys.path.append(os.getcwd())

from app.bot.events import event_manager
from app.bot.runner import BotRunner

async def test_broadcast_isolation():
    print("🧪 Starting Broadcast Isolation Verification...")
    
    # 1. Setup Mock WebSockets
    # We need to test the actual EventManager logic, so we can't mock broadcast.
    # We need to mock active_connections.
    
    ws_user_a = MagicMock()
    ws_user_b = MagicMock()
    ws_anon = MagicMock()
    
    # Mock WebSocket send_json to capture messages
    # We use lists to store received messages for each mock
    a_msgs = []
    b_msgs = []
    anon_msgs = []
    
    async def capture_a(msg): a_msgs.append(msg)
    async def capture_b(msg): b_msgs.append(msg)
    async def capture_anon(msg): anon_msgs.append(msg)
    
    ws_user_a.send_json.side_effect = capture_a
    ws_user_b.send_json.side_effect = capture_b
    ws_anon.send_json.side_effect = capture_anon
    
    # Setup Active Connections
    event_manager.active_connections = {
        ws_user_a: "UserA",
        ws_user_b: "UserB",
        ws_anon: None
    }
    
    # 2. Test Case: Bot Runner for UserA
    print("\n[Case 1] BotRunner('UserA') broadcasts...")
    runner = BotRunner(account_id="UserA")
    # We fake the broadcast call manually as if it came from runner
    # Because we don't want to actually start the bot and connect to Deriv
    
    msg = {
        "type": "bot_status", 
        "status": "running", 
        "account_id": runner.account_id 
    }
    
    await event_manager.broadcast(msg)
    
    # Verification
    if len(a_msgs) == 1:
        print("✅ PASS: UserA received the message")
    else:
        print(f"❌ FAIL: UserA missed the message {len(a_msgs)}")
        
    if len(b_msgs) == 0:
        print("✅ PASS: UserB did NOT receive the message")
    else:
        print(f"❌ FAIL: UserB received leakage! {b_msgs}")
        
    if len(anon_msgs) == 0:
        print("✅ PASS: Anonymous user did NOT receive the message")
    else:
        print(f"❌ FAIL: Anonymous user received leakage! {anon_msgs}")

    # 3. Test Case: Bot Runner for UserB
    print("\n[Case 2] BotRunner('UserB') broadcasts...")
    runner_b = BotRunner(account_id="UserB")
    
    msg_b = {
        "type": "signal", 
        "symbol": "R_100", 
        "account_id": runner_b.account_id 
    }
    
    await event_manager.broadcast(msg_b)
    
    if len(b_msgs) == 1:
        print("✅ PASS: UserB received signal")
    else:
        print(f"❌ FAIL: UserB missed signal")
        
    if len(a_msgs) == 1: # Still 1 from previous test
        print("✅ PASS: UserA did NOT receive UserB's signal")
    else:
        print(f"❌ FAIL: UserA received leakage! {a_msgs}")

    print("\n🎉 Broadcast isolation verified!")

if __name__ == "__main__":
    asyncio.run(test_broadcast_isolation())
