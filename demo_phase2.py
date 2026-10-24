"""
Simulated demonstration of Beru Phase 2:
1. Phone and PC pair and connect over WebSockets.
2. Phone sends 'lock my pc' (Text Command):
   - Hub interprets intent -> lock_device on PC.
   - Confirmation gate requires approval ('hard').
   - Phone receives 'confirm_request' and replies 'confirm'.
   - PC receives 'execute' and executes 'lock'.
3. Phone sends 'set an alarm for 6 am':
   - Hub interprets intent -> set_alarm on Phone.
   - Confirmation: 'none'.
   - Phone receives 'execute' directly and confirms alarm set.
4. Phone sends incomplete 'send a message':
   - Hub asks for clarification: missing 'recipient'.
   - Phone responds: 'to Alice saying Meeting in 10 mins'.
   - Hub fills slots and requests confirmation ('hard').
   - Phone confirms and executes.
"""

import sys
import time
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.skills import init_skills

def run_phase2_demo():
    print("=" * 65)
    print("      BERU PHASE 2: NATURAL LANGUAGE & INTENT ROUTING DEMO")
    print("=" * 65)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_skills()

    client = TestClient(app)

    # 1. Register Phone and pair PC
    print("\n[Setup] Registering Phone (Android) and pairing PC (Windows)...")
    res_phone = client.post("/register-first-device", json={
        "device_name": "Pixel 8",
        "platform": "android",
        "capabilities": ["notify", "set_alarm", "send_message", "flashlight"]
    })
    phone_data = res_phone.json()
    phone_token = phone_data["token"]

    res_pair = client.post("/pair/start", headers={"Authorization": f"Bearer {phone_token}"})
    code = res_pair.json()["code"]

    res_pc = client.post("/pair/complete", json={
        "code": code,
        "device_name": "Workstation Windows",
        "platform": "windows",
        "capabilities": ["lock", "volume", "open_app"]
    })
    pc_data = res_pc.json()
    pc_token = pc_data["token"]
    print(" -> Both devices paired successfully!")

    # 2. Open WebSocket connections for Phone and PC
    with client.websocket_connect(f"/ws?token={phone_token}") as ws_phone:
        _ = ws_phone.receive_json()

        with client.websocket_connect(f"/ws?token={pc_token}") as ws_pc:
            _ = ws_phone.receive_json()  # PC online notice
            _ = ws_pc.receive_json()     # Initial devices list

            # --- Scenario A: 'lock my PC' with confirmation ---
            print("\n" + "-" * 60)
            print("[Scenario A] Phone sends text: 'lock my PC'")
            print("-" * 60)
            ws_phone.send_json({
                "type": "text_command",
                "text": "lock my PC"
            })

            # Confirmation gate triggers because lock_device is 'hard'
            confirm_req = ws_phone.receive_json()
            print(f" -> Hub response to Phone: {confirm_req['type']}")
            print(f"    Prompt: '{confirm_req['prompt']}'")
            print(f"    Target Device: {confirm_req['target']}, Skill: {confirm_req['skill']}")
            assert confirm_req["type"] == "confirm_request"
            conf_id = confirm_req["confirmation_id"]

            # Phone user confirms
            print(f" -> Phone user taps 'Confirm' (sending confirmation_id={conf_id})...")
            ws_phone.send_json({
                "type": "confirm",
                "confirmation_id": conf_id
            })

            # PC receives execute command
            pc_exec = ws_pc.receive_json()
            print(f" -> PC received execute message: action='{pc_exec['action']}', from='{pc_exec['from_device']}'")
            assert pc_exec["action"] == "lock"

            # PC sends result ok
            ws_pc.send_json({
                "type": "result",
                "command_id": pc_exec["command_id"],
                "status": "ok",
                "data": {"locked": True}
            })

            # Phone receives final success status
            final_status = ws_phone.receive_json()
            print(f" -> Phone received final status: {final_status['status']}")
            assert final_status["status"] == "ok"

            # --- Scenario B: 'set an alarm for 6 am' on Phone ---
            print("\n" + "-" * 60)
            print("[Scenario B] Phone sends text: 'set an alarm for 6 am'")
            print("-" * 60)
            ws_phone.send_json({
                "type": "text_command",
                "text": "set an alarm for 6 am"
            })

            # Target is phone, confirmation is none -> Phone immediately receives execute!
            phone_exec = ws_phone.receive_json()
            print(f" -> Phone received execute: action='{phone_exec['action']}', params={phone_exec['params']}")
            assert phone_exec["action"] == "set_alarm"
            assert phone_exec["params"]["time"] == "6 am"

            # Phone confirms alarm set locally
            ws_phone.send_json({
                "type": "result",
                "command_id": phone_exec["command_id"],
                "status": "ok",
                "data": {"alarm_set": "06:00"}
            })

            alarm_status = ws_phone.receive_json()
            print(f" -> Alarm status confirmed: {alarm_status['status']}")
            assert alarm_status["status"] == "ok"

            # --- Scenario C: Slot filling and confirmation for 'send a message' ---
            print("\n" + "-" * 60)
            print("[Scenario C] Phone sends incomplete text: 'send a message'")
            print("-" * 60)
            ws_phone.send_json({
                "type": "text_command",
                "text": "send a message"
            })

            clarify_msg = ws_phone.receive_json()
            print(f" -> Hub asks clarification: '{clarify_msg['question']}'")
            print(f"    Missing slots: {clarify_msg['missing_slots']}")
            assert clarify_msg["type"] == "clarify"
            assert "recipient" in clarify_msg["missing_slots"]

            print(" -> Phone user replies: 'to Alice saying Meeting in 10 mins'")
            ws_phone.send_json({
                "type": "text_command",
                "text": "to Alice saying Meeting in 10 mins"
            })

            # Slots are filled; send_message has 'hard' confirmation
            msg_confirm = ws_phone.receive_json()
            print(f" -> Hub requested confirmation: '{msg_confirm['prompt']}'")
            assert msg_confirm["type"] == "confirm_request"
            msg_conf_id = msg_confirm["confirmation_id"]

            print(" -> Phone user confirms...")
            ws_phone.send_json({
                "type": "confirm",
                "confirmation_id": msg_conf_id
            })

            # Phone receives execute
            msg_exec = ws_phone.receive_json()
            print(f" -> Phone executing send_message: {msg_exec['params']}")
            assert msg_exec["action"] == "send_message"
            assert msg_exec["params"]["recipient"] == "Alice"
            assert msg_exec["params"]["message"] == "Meeting in 10 mins"

            ws_phone.send_json({
                "type": "result",
                "command_id": msg_exec["command_id"],
                "status": "ok",
                "data": {"sent": True}
            })

            msg_final = ws_phone.receive_json()
            print(f" -> Message sent status confirmed: {msg_final['status']}")
            assert msg_final["status"] == "ok"

    print("\n" + "=" * 65)
    print("SUCCESS: Phase 2 end-to-end natural language & intent routing verified!")
    print("=" * 65)

if __name__ == "__main__":
    run_phase2_demo()
