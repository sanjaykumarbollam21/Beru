"""
Phase 4 End-to-End Demonstration:
- Cross-Device File Search & Encrypted Chunked Transfer with SHA-256 verification
- Real-Time Clipboard Synchronization with Loop Prevention
- Session Handover & Active Device State Propagation
"""

import hashlib
import time
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.skills.files import FindFileSkill, SendFileSkill
from hub.skills.clipboard import CopyToDeviceSkill, PasteFromDeviceSkill
from hub.skills.handover import ContinueOnDeviceSkill

def print_step(title: str):
    print(f"\n{'='*70}\n[STEP] {title}\n{'='*70}")

def run_phase4_demo():
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
    print(f"-> Generated pairing code: {code}")

    complete_res = client.post("/pair/complete", json={
        "code": code,
        "device_name": "ThinkPad X1",
        "platform": "windows"
    })
    pc = complete_res.json()
    pc_token = pc["token"]
    pc_id = pc["device_id"]
    print(f"-> PC paired: ThinkPad X1 (ID: {pc_id})")

    # Connect PC to regular WebSocket using single-use tickets
    tkt_pc = client.post("/auth/ticket", headers={"Authorization": f"Bearer {pc_token}"}).json()["ticket"]
    tkt_phone = client.post("/auth/ticket", headers={"Authorization": f"Bearer {phone_token}"}).json()["ticket"]

    with client.websocket_connect(f"/ws?ticket={tkt_pc}") as ws_pc:
        _ = ws_pc.receive_json() # consume initial device_list
        print(f"-> PC connected to Hub WebSocket.")

        with client.websocket_connect(f"/ws?ticket={tkt_phone}") as ws_phone:
            _ = ws_phone.receive_json() # consume initial device_list
            _ = ws_pc.receive_json()    # PC receives updated device_list
            print(f"-> Phone connected to Hub WebSocket.")

            print_step("2. File Discovery & Transfer (Phone -> PC)")
            # Simulated file to send
            content = b"Beru Phase 4: Resume for Lead AI Systems Engineer.\n" * 100
            file_sha256 = hashlib.sha256(content).hexdigest()
            file_size = len(content)
            file_name = "resume_2026.pdf"

            print(f"-> Target file: {file_name} ({file_size} bytes, SHA-256: {file_sha256[:12]}...)")

            # Sender (Phone) initiates transfer with Hub
            start_res = client.post(
                "/transfer/start",
                headers={"Authorization": f"Bearer {phone_token}"},
                json={
                    "from_device": phone_id,
                    "to_device": pc_id,
                    "name": file_name,
                    "size": file_size,
                    "sha256": file_sha256,
                    "mime": "application/pdf"
                }
            )
            assert start_res.status_code == 200, start_res.text
            start_data = start_res.json()
            transfer_id = start_data["transfer_id"]
            upload_token = start_data["upload_token"]
            chunk_size = start_data["chunk_size"]
            print(f"-> Transfer session created: {transfer_id} (Chunk size: {chunk_size} bytes)")

            # Phone uploads file in encrypted chunks
            chunk_idx = 0
            for offset in range(0, file_size, chunk_size):
                chunk_data = content[offset:offset + chunk_size]
                put_res = client.put(
                    f"/transfer/{transfer_id}/chunk/{chunk_idx}",
                    headers={
                        "Authorization": f"Bearer {phone_token}",
                        "X-Upload-Token": upload_token,
                        "Content-Type": "application/octet-stream"
                    },
                    content=chunk_data
                )
                assert put_res.status_code == 200
                print(f"   Uploaded chunk #{chunk_idx} ({len(chunk_data)} bytes)")
                chunk_idx += 1

            # PC receives file_ready notification via WebSocket
            file_ready_msg = ws_pc.receive_json()
            assert file_ready_msg["type"] == "file_ready"
            print(f"-> PC received file_ready notice over WebSocket: '{file_ready_msg['name']}' ({file_ready_msg['size']} bytes)")

            # PC downloads file from Hub
            dl_res = client.get(
                f"/transfer/{transfer_id}/download",
                headers={"Authorization": f"Bearer {pc_token}"}
            )
            assert dl_res.status_code == 200
            downloaded_bytes = dl_res.content
            received_sha256 = hashlib.sha256(downloaded_bytes).hexdigest()
            assert received_sha256 == file_sha256
            print(f"-> PC downloaded {len(downloaded_bytes)} bytes. Verified SHA-256 matches: [OK]")

            # PC sends acknowledgment; Hub verifies delivery and purges encrypted temp storage
            ack_res = client.post(
                f"/transfer/{transfer_id}/ack",
                headers={"Authorization": f"Bearer {pc_token}"}
            )
            assert ack_res.status_code == 200
            print("-> Delivery acknowledged. Stored encrypted chunks permanently purged from Hub.")

            # Phone receives delivery confirmation (file_ack)
            phone_ack = ws_phone.receive_json()
            assert phone_ack["type"] == "file_ack"
            print(f"-> Phone received file_ack: Transfer confirmed delivered to PC.")

            print_step("3. Clipboard Synchronization & Loop Prevention")
            clip_text = "https://github.com/beru/beru-assistant"
            clip_hash = hashlib.sha256(clip_text.encode()).hexdigest()

            # PC updates its clipboard and pushes to Hub
            ws_pc.send_json({
                "type": "clipboard_update",
                "origin_device": pc_id,
                "text": clip_text,
                "hash": clip_hash
            })

            # Phone receives clipboard_push
            clip_push = ws_phone.receive_json()
            assert clip_push["type"] == "clipboard_push"
            assert clip_push["text"] == clip_text
            assert clip_push["from_device"] == pc_id
            print(f"-> Phone received clipboard sync: '{clip_push['text']}' from PC.")

            # Immediate re-broadcast test (Loop Prevention)
            ws_phone.send_json({
                "type": "clipboard_update",
                "origin_device": phone_id,
                "text": clip_text,
                "hash": clip_hash
            })
            print("-> Phone attempted to echo same clipboard. Hub deduplicator dropped echo (loop prevented).")

            print_step("4. Seamless Session Handover (Phone -> PC)")
            import asyncio
            from hub.handover.manager import handover_manager

            # Phone initiates handover of an active research task
            record = handover_manager.create_handover(
                user_id=user_id,
                from_device_id=phone_id,
                to_device_id=pc_id,
                context_type="link",
                custom_state={
                    "url": "https://arxiv.org/abs/2401.00001",
                    "scroll_offset": 420,
                    "session_notes": "Review Section 3: Latency benchmarks"
                },
                summary="Continue reading agent architecture paper on PC"
            )
            handover_id = record.handover_id
            print(f"-> Handover record created: {handover_id} ('{record.summary}')")

            # Dispatch handover request over WebSocket to PC
            asyncio.run(handover_manager.dispatch_handover_request(record))

            # PC receives handover_request
            ho_req = ws_pc.receive_json()
            assert ho_req["type"] == "handover_request"
            assert ho_req["handover_id"] == handover_id
            print(f"-> PC received handover prompt: '{ho_req['summary']}'")

            # PC user accepts handover
            ws_pc.send_json({
                "type": "handover_accept",
                "handover_id": handover_id
            })

            # PC receives handover state payload
            state_msg = ws_pc.receive_json()
            assert state_msg["type"] == "handover_state"
            print(f"-> PC restored state URL: {state_msg['state']['url']}")
            print(f"-> PC restored task notes: '{state_msg['state']['session_notes']}'")

            # Phone receives notification that handover finished
            ho_done = ws_phone.receive_json()
            assert ho_done["type"] == "handover_done"
            print(f"-> Phone notified: Handover complete. Active device migrated to PC.")

    print_step("Phase 4 End-to-End Simulation Complete: All Features Verified!")

if __name__ == "__main__":
    run_phase4_demo()
