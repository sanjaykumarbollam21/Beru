"""
Phase 5 End-to-End Demonstration:
- Wake Word Arbitration across Phone and PC (Weighted Scoring, Hysteresis, and Pinned Override)
- Explicit Personalization (Default Targets, Preferred Apps, Contact Nicknames)
- Transparent Learning from Repeated Corrections with User Confirmation
- Remembered Facts (Store, Search, and Recall)
- Saved Multi-Step Routines with Per-Step Confirmation Rules
"""

import time
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.personalization.store import preference_store
from hub.personalization.learner import learner
from hub.personalization.routines import routine_manager
from hub.intent.resolver import intent_resolver

def print_step(title: str):
    print(f"\n{'='*70}\n[STEP] {title}\n{'='*70}")

def run_phase5_demo():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(app)

    print_step("1. Initialize and Pair Phone (Android) and PC (Windows)")
    reg_res = client.post("/register-first-device", json={
        "device_name": "Pixel 8 Pro",
        "platform": "android"
    })
    phone = reg_res.json()
    user_id = phone["user_id"]
    phone_token = phone["token"]
    phone_id = phone["device_id"]
    print(f"-> Phone registered: Pixel 8 Pro (ID: {phone_id})")

    pair_res = client.post("/pair/start", headers={"Authorization": f"Bearer {phone_token}"})
    code = pair_res.json()["code"]

    complete_res = client.post("/pair/complete", json={
        "code": code,
        "device_name": "ThinkPad X1",
        "platform": "windows"
    })
    pc = complete_res.json()
    pc_token = pc["token"]
    pc_id = pc["device_id"]
    print(f"-> PC paired: ThinkPad X1 (ID: {pc_id})")

    with client.websocket_connect(f"/ws?token={phone_token}") as ws_phone:
        _ = ws_phone.receive_json()

        with client.websocket_connect(f"/ws?token={pc_token}") as ws_pc:
            _ = ws_phone.receive_json()
            _ = ws_pc.receive_json()
            print("-> Both Phone and PC connected to Hub WebSocket.")

            print_step("2. Wake Word Arbitration (Speaker closer to PC)")
            print("-> User speaks 'Hey Beru' while sitting at PC desk.")
            
            # Phone sends claim with lower loudness
            ws_phone.send_json({
                "type": "wake_claim",
                "claim_id": "phone-c1",
                "detector_score": 0.70,
                "signal_level": 0.40,
                "screen_on": False,
                "in_use": False
            })

            # PC sends claim with high loudness & in_use
            ws_pc.send_json({
                "type": "wake_claim",
                "claim_id": "pc-c1",
                "detector_score": 0.92,
                "signal_level": 0.88,
                "screen_on": True,
                "in_use": True,
                "charging": True
            })

            msg_phone = ws_phone.receive_json()
            msg_pc = ws_pc.receive_json()

            assert msg_phone["type"] == "wake_lose"
            assert msg_pc["type"] == "wake_win"
            print(f"-> Hub Decision: PC won (wake_win), Phone lost (wake_lose, stays silent).")

            print_step("3. Manual Override: Pinned Preferred Wake Device")
            print("-> Waiting for utterance cooldown (2.1s)...")
            time.sleep(2.1)
            print("-> User pins Phone as preferred wake device in settings.")
            preference_store.set_preference(user_id, "preferred_wake_device", phone_id)

            ws_phone.send_json({
                "type": "wake_claim",
                "claim_id": "phone-c2",
                "detector_score": 0.70,
                "signal_level": 0.35
            })
            ws_pc.send_json({
                "type": "wake_claim",
                "claim_id": "pc-c2",
                "detector_score": 0.95,
                "signal_level": 0.90
            })

            msg_phone2 = ws_phone.receive_json()
            msg_pc2 = ws_pc.receive_json()

            assert msg_phone2["type"] == "wake_win"
            assert msg_pc2["type"] == "wake_lose"
            print("-> Pinned device override verified: Phone wins arbitration!")

    print_step("4. Explicit Personalization & Target Overrides")
    # By default, volume command without explicit target targets self (android)
    import asyncio
    res_default = asyncio.run(intent_resolver.resolve("set volume to 30", sender_platform="android", user_id=user_id))
    print(f"-> Before preference: 'set volume to 30' targets: {res_default[0].target_platform}")

    # Set user preference: default target for set_volume is windows
    preference_store.set_preference(user_id, "default_targets", {"set_volume": "windows"})
    res_pref = asyncio.run(intent_resolver.resolve("set volume to 30", sender_platform="android", user_id=user_id))
    print(f"-> After preference: 'set volume to 30' automatically targets: {res_pref[0].target_platform}")
    assert res_pref[0].target_platform == "windows"

    print_step("5. Transparent Learning from Repeated Corrections")
    print("-> User runs lock command, correcting from PC to Phone 3 times...")
    sug1 = learner.record_correction(user_id, "lock_device", intended_target="windows", corrected_target="android")
    print(f"   Correction 1: Recorded. (Suggestion: {sug1})")
    sug2 = learner.record_correction(user_id, "lock_device", intended_target="windows", corrected_target="android")
    print(f"   Correction 2: Recorded. (Suggestion: {sug2})")
    sug3 = learner.record_correction(user_id, "lock_device", intended_target="windows", corrected_target="android")
    print(f"   Correction 3: BERU PROMPTS USER -> '{sug3}'")
    assert sug3 is not None and "Should I always do that on your phone?" in sug3

    # User accepts suggestion
    learner.accept_correction_suggestion(user_id, "lock_device", "android")
    records = preference_store.get_all_preference_records(user_id)
    lock_pref = next(r for r in records if r["key"] == "default_targets")
    print(f"-> User confirmed 'yes'. Saved preference: {lock_pref['value']} (Source: {lock_pref['source']})")
    assert lock_pref["source"] == "learned"

    print_step("6. Remembered Facts (Store, Search & Recall)")
    fact_id = preference_store.add_fact(user_id, "My gym locker combination is 24-18-09")
    print(f"-> User: 'Remember that my gym locker combination is 24-18-09' (Fact ID: {fact_id})")

    recalled = preference_store.search_facts(user_id, "gym locker")
    print(f"-> User: 'What did I tell you about my gym locker?'")
    print(f"-> Beru: Found 1 remembered note: '{recalled[0]['text']}'")
    assert "24-18-09" in recalled[0]["text"]

    print_step("7. Saved Multi-Step Routines & Safety Gates")
    routine_manager.create_routine(
        user_id=user_id,
        name="work mode",
        steps=[
            {"skill": "set_volume", "target": "windows", "params": {"level": 20}},
            {"skill": "lock_device", "target": "windows", "params": {}}
        ]
    )
    print("-> Routine 'work mode' created: [1. set_volume to 20, 2. lock_device]")

    plan = asyncio.run(intent_resolver.resolve("work mode", sender_platform="android", user_id=user_id))
    print(f"-> User says 'work mode': Resolved into {len(plan)}-step plan:")
    for idx, p in enumerate(plan):
        print(f"   Step {idx+1}: {p.skill.name} on {p.target_platform} (Requires confirmation: {p.requires_confirmation})")
    assert plan[1].requires_confirmation is True  # lock_device has 'hard' confirmation gate!

    print_step("Phase 5 End-to-End Simulation Complete: All Features Verified!")

if __name__ == "__main__":
    run_phase5_demo()
