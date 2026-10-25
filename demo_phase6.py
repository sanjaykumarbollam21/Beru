"""
Phase 6 Demonstration: Hardening, Reliability, and Packaging.
Simulates end-to-end security hardening, ticket auth, device revocation,
command idempotency, circuit breakers, Prometheus metrics, and encrypted backups.
"""

import os
import sys
import time
import shutil
import sqlite3
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine, SessionLocal, User, Device, UserPreference, utcnow
from hub.skills import init_skills
from hub.security.tickets import ticket_manager
from hub.security.ratelimit import pairing_lockout
from hub.reliability.breaker import circuit_registry, CircuitBreaker, CircuitState
from hub.reliability.idempotency import idempotency_store
from hub.backup.backup import DatabaseBackupManager

def print_step(title: str):
    print("\n" + "=" * 70)
    print(f"[STEP] {title}")
    print("=" * 70)

def run_phase6_demo():
    print("Initializing Beru Phase 6 Hardening & Reliability Simulation...")
    init_skills()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    circuit_registry.reset_all()

    with TestClient(app) as client:
        # =====================================================================
        # 1. Pairing Hardening & Lockout Defense
        # =====================================================================
        print_step("1. Pairing Hardening & Lockout Defense")
        print("-> Registering first device: Pixel 8 Pro...")
        reg_res = client.post("/register-first-device", json={
            "device_name": "Pixel 8 Pro",
            "platform": "android",
            "capabilities": ["lock_device", "set_volume"]
        })
        phone = reg_res.json()
        phone_token = phone["token"]
        user_id = phone["user_id"]
        phone_id = phone["device_id"]
        print(f"-> Phone registered: ID={phone_id}")

        print("-> Attacker attempts brute-forcing pairing codes (5 invalid attempts)...")
        test_ip = "192.168.1.99"
        pairing_lockout.reset(test_ip)
        for i in range(5):
            pairing_lockout.record_failure(test_ip)

        is_locked, rem = pairing_lockout.is_locked(test_ip)
        print(f"-> Lockout status: locked={is_locked}, duration={int(rem)} seconds remaining.")
        assert is_locked is True

        # Reset lockout to proceed with legitimate pairing
        pairing_lockout.reset(test_ip)
        start_res = client.post("/pair/start", headers={"Authorization": f"Bearer {phone_token}"})
        code = start_res.json()["code"]
        print(f"-> Primary device generated pairing code: {code}")

        pair_res = client.post("/pair/complete", json={
            "code": code,
            "device_name": "ThinkPad X1",
            "platform": "windows",
            "capabilities": ["lock_device", "set_volume"]
        })
        pc = pair_res.json()
        pc_token = pc["token"]
        pc_id = pc["device_id"]
        print(f"-> Second device paired: ThinkPad X1 (ID: {pc_id})")

        # =====================================================================
        # 2. WebSocket Tickets (No Tokens in URLs)
        # =====================================================================
        print_step("2. Short-Lived Single-Use WebSocket Tickets")
        print("-> Requesting short-lived ticket via POST /auth/ticket (Authorization: Bearer)...")
        tkt_res = client.post("/auth/ticket", headers={"Authorization": f"Bearer {phone_token}"})
        ticket_data = tkt_res.json()
        tkt = ticket_data["ticket"]
        print(f"-> Issued ticket: {tkt[:15]}... (TTL: {ticket_data['expires_in']}s)")

        print("-> Connecting to WebSocket gateway using ?ticket=...")
        with client.websocket_connect(f"/ws?ticket={tkt}&protocol_version=2.0") as ws:
            init_msg = ws.receive_json()
            print(f"-> WebSocket accepted connection. Initial payload: type={init_msg['type']}, online={len(init_msg['online'])}")

        print("-> Attempting ticket reuse (Replay Attack Prevention)...")
        reused = ticket_manager.consume_ticket(tkt)
        print(f"-> Replay attempt outcome: {reused} (Ticket was rejected!)")
        assert reused is None

        # =====================================================================
        # 3. Device Management: Token Rotation & Immediate Revocation
        # =====================================================================
        print_step("3. Device Management: Token Rotation & Revocation")
        list_res = client.get("/devices", headers={"Authorization": f"Bearer {phone_token}"})
        devices = list_res.json()["devices"]
        print(f"-> Paired devices for user ({len(devices)}): {[d['name'] for d in devices]}")

        print("-> Rotating token for ThinkPad X1...")
        rot_res = client.post(f"/devices/{pc_id}/rotate-token", headers={"Authorization": f"Bearer {phone_token}"})
        new_token = rot_res.json()["new_token"]
        print(f"-> Token rotated successfully: new_token={new_token[:10]}...")

        print("-> Revoking ThinkPad X1 via DELETE /devices/{id}...")
        del_res = client.delete(f"/devices/{pc_id}", headers={"Authorization": f"Bearer {phone_token}"})
        print(f"-> Revoke outcome: {del_res.json()}")

        # Verify revoked device cannot get tickets
        fail_tkt = client.post("/auth/ticket", headers={"Authorization": f"Bearer {new_token}"})
        print(f"-> Revoked device authentication attempt: HTTP {fail_tkt.status_code} (Cut off immediately)")
        assert fail_tkt.status_code == 401

        # =====================================================================
        # 4. Command Idempotency (Deduplication)
        # =====================================================================
        print_step("4. Command Idempotency & Deduplication")
        cmd_id = "demo-cmd-unique-999"
        print(f"-> Dispatching command with ID: {cmd_id}")
        is_dup1, _ = idempotency_store.check_or_set(cmd_id)
        idempotency_store.complete(cmd_id, {"status": "ok", "locked": True})
        print(f"   First dispatch: is_duplicate={is_dup1} (Executed)")

        print("-> Simulating network drop and client retry with same command ID...")
        is_dup2, cached_result = idempotency_store.check_or_set(cmd_id)
        print(f"   Retry dispatch: is_duplicate={is_dup2}, cached_result={cached_result}")
        assert is_dup2 is True

        # =====================================================================
        # 5. Reliability: Circuit Breaker & Failover
        # =====================================================================
        print_step("5. Provider Circuit Breaker Resilience")
        breaker = circuit_registry.get_breaker("cloud_llm_groq", failure_threshold=3, recovery_timeout=0.2)
        print(f"-> Initial circuit breaker state: {breaker.state.value} (can_execute={breaker.can_execute()})")

        print("-> Simulating 3 consecutive cloud provider timeouts/failures...")
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        print(f"-> Circuit breaker tripped: state={breaker.state.value} (can_execute={breaker.can_execute()})")
        assert breaker.state == CircuitState.OPEN

        print("-> Waiting for breaker recovery timeout (0.2s)...")
        time.sleep(0.22)
        print(f"-> After recovery window: state={breaker.state.value} (can_execute={breaker.can_execute()})")
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_success()
        print(f"-> Successful trial request restores circuit to: {breaker.state.value}")
        assert breaker.state == CircuitState.CLOSED

        # =====================================================================
        # 6. Observability: Health & Prometheus Metrics
        # =====================================================================
        print_step("6. Observability: Health Check & Prometheus Metrics")
        health_data = client.get("/health").json()
        print("-> GET /health:")
        print(f"   Status: {health_data['status']}, DB: {health_data['database']}, Uptime: {health_data['uptime_seconds']}s")

        metrics_text = client.get("/metrics").text
        print("-> GET /metrics (sample Prometheus output):")
        for line in metrics_text.strip().split("\n")[:8]:
            print(f"   {line}")

        # =====================================================================
        # 7. Backup & Recovery: Encrypted Snapshot & Integrity Restore
        # =====================================================================
        print_step("7. Backup & Recovery: Encrypted Snapshot & Integrity Restore")
        backup_dir = "./data/demo_backups"
        os.makedirs(backup_dir, exist_ok=True)
        backup_mgr = DatabaseBackupManager(backup_dir=backup_dir, retention_count=14)

        # Store a preference to verify after restore
        with SessionLocal() as db:
            p = UserPreference(
                id="pref-demo-p6",
                user_id=user_id,
                key="default_browser",
                value="Firefox",
                source="user"
            )
            db.add(p)
            db.commit()

        backup_file = backup_mgr.create_backup()
        print(f"-> Encrypted backup created: {backup_file}")
        with open(backup_file, "rb") as f:
            enc_sample = f.read()[:32]
        print(f"-> Encrypted file header (raw ciphertext): {enc_sample}")

        # Restore into clean DB
        clean_db = os.path.join(backup_dir, "restored_demo.db")
        backup_mgr.restore_backup(backup_file, target_db_path=clean_db)
        print(f"-> Restored backup to: {clean_db}")

        # Verify integrity
        conn = sqlite3.connect(clean_db)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM user_preferences WHERE id = 'pref-demo-p6'")
        restored_row = cursor.fetchone()
        conn.close()
        print(f"-> Restored data check: key='{restored_row[0]}', value='{restored_row[1]}'")
        assert restored_row[0] == "default_browser"

        # Cleanup demo backup dir
        shutil.rmtree(backup_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print("[SUCCESS] Phase 6 Hardening, Reliability, and Packaging Verified!")
    print("=" * 70)

if __name__ == "__main__":
    run_phase6_demo()
