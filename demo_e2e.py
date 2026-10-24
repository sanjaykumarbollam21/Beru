"""
Simulated end-to-end demonstration of Beru Phase 1:
1. 'Phone' registers as the first device.
2. 'Phone' generates a pairing code.
3. 'PC' completes pairing using the code and registers 'lock' capability.
4. Both devices connect to the WebSocket endpoint.
5. 'Phone' sends a 'lock' command targeting 'windows'.
6. 'PC' receives the 'execute' message, executes lock, and returns the result.
7. 'Phone' receives the final 'ok' status.
"""

import sys
import uuid
import time
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine

def run_e2e_simulation():
    print("=" * 60)
    print("      BERU PHASE 1: END-TO-END DEMO SIMULATION")
    print("=" * 60)

    # Clean test DB
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    client = TestClient(app)

    # Step 1: Phone registers as bootstrap first device
    print("\n[Step 1] Phone calls POST /register-first-device...")
    res_phone = client.post("/register-first-device", json={
        "device_name": "Pixel 8",
        "platform": "android",
        "capabilities": ["notify", "tts"]
    })
    if res_phone.status_code != 200:
        print(f"Failed to register first device: {res_phone.text}")
        sys.exit(1)

    phone_data = res_phone.json()
    phone_token = phone_data["token"]
    user_id = phone_data["user_id"]
    print(f" -> Phone registered! User ID: {user_id}, Phone Device ID: {phone_data['device_id']}")

    # Step 2: Phone initiates pairing code
    print("\n[Step 2] Phone calls POST /pair/start...")
    res_pair = client.post(
        "/pair/start",
        headers={"Authorization": f"Bearer {phone_token}"}
    )
    pair_data = res_pair.json()
    pairing_code = pair_data["code"]
    print(f" -> Pairing code generated: {pairing_code}")
    print(f" -> QR Payload: {pair_data['qr_payload']}")
    print(f" -> Code expires at: {pair_data['expires_at']}")

    # Step 3: PC scans code and completes pairing
    print("\n[Step 3] PC calls POST /pair/complete with pairing code...")
    res_pc = client.post("/pair/complete", json={
        "code": pairing_code,
        "device_name": "Workstation Windows",
        "platform": "windows",
        "capabilities": ["lock", "volume", "open_browser"]
    })
    if res_pc.status_code != 200:
        print(f"Failed to complete pairing: {res_pc.text}")
        sys.exit(1)

    pc_data = res_pc.json()
    pc_token = pc_data["token"]
    print(f" -> PC paired successfully! PC Device ID: {pc_data['device_id']}")

    # Step 4: Both devices connect to WebSocket endpoint
    print("\n[Step 4] Connecting Phone and PC to /ws...")
    with client.websocket_connect(f"/ws?token={phone_token}") as ws_phone:
        msg_phone_init = ws_phone.receive_json()
        print(f" -> Phone connected! Online devices: {[d['name'] for d in msg_phone_init['online']]}")

        with client.websocket_connect(f"/ws?token={pc_token}") as ws_pc:
            msg_phone_updated = ws_phone.receive_json()
            msg_pc_init = ws_pc.receive_json()
            print(f" -> PC connected! Phone notified of online devices: {[d['name'] for d in msg_phone_updated['online']]}")

            # Step 5: Phone sends command to lock PC
            cmd_id = f"cmd-{uuid.uuid4().hex[:8]}"
            print(f"\n[Step 5] Phone sends command '{cmd_id}': action='lock', target='windows'...")
            ws_phone.send_json({
                "type": "command",
                "id": cmd_id,
                "action": "lock",
                "target": "windows",
                "params": {"message": "Locking workstation"}
            })

            # Step 6: Phone receives delivered status
            delivered_status = ws_phone.receive_json()
            print(f" -> Phone received status: {delivered_status}")
            assert delivered_status["status"] == "delivered"

            # Step 7: PC receives execute message
            exec_msg = ws_pc.receive_json()
            print(f"\n[Step 6] PC received execution request: {exec_msg}")
            assert exec_msg["action"] == "lock"

            # Step 8: PC simulates execution and sends back result
            print(" -> PC simulated action 'lock': [Workstation locked]")
            ws_pc.send_json({
                "type": "result",
                "command_id": cmd_id,
                "status": "ok",
                "data": {
                    "action": "lock",
                    "locked": True,
                    "timestamp": time.time()
                }
            })

            # Step 9: Phone receives final result
            final_status = ws_phone.receive_json()
            print(f"\n[Step 7] Phone received command result: {final_status}")
            assert final_status["status"] == "ok"
            assert final_status["data"]["locked"] is True

    print("\n" + "=" * 60)
    print("SUCCESS: End-to-end device pairing & command routing verified!")
    print("=" * 60)

if __name__ == "__main__":
    run_e2e_simulation()
