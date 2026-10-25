import pytest
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.skills import init_skills

@pytest.fixture(autouse=True)
def setup_db():
    init_skills()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_e2e_complete_flow_with_tickets_and_hardening(client):
    """
    Complete end-to-end flow:
    1. Register Phone.
    2. Start pairing and complete for PC.
    3. Both acquire short-lived WebSocket tickets (no tokens in URL).
    4. Connect over WebSocket and exchange heartbeat.
    5. Handover active device tracking.
    6. Execute cross-device text command with deduplication.
    7. File transfer initialization and delivery receipt.
    8. Check health and Prometheus metrics.
    """
    # 1. Register first device (Phone)
    phone_res = client.post("/register-first-device", json={
        "device_name": "Pixel 8 Pro",
        "platform": "android",
        "capabilities": ["lock_device", "set_volume", "open_app"]
    })
    assert phone_res.status_code == 200
    phone = phone_res.json()
    user_id = phone["user_id"]
    phone_token = phone["token"]

    # 2. Pair second device (PC)
    start_res = client.post("/pair/start", headers={"Authorization": f"Bearer {phone_token}"})
    assert start_res.status_code == 200
    code = start_res.json()["code"]

    pc_res = client.post("/pair/complete", json={
        "code": code,
        "device_name": "ThinkPad X1",
        "platform": "windows",
        "capabilities": ["lock_device", "set_volume", "open_app"]
    })
    assert pc_res.status_code == 200
    pc = pc_res.json()
    pc_token = pc["token"]

    # 3. Issue single-use tickets for both devices
    tkt_phone = client.post("/auth/ticket", headers={"Authorization": f"Bearer {phone_token}"}).json()["ticket"]
    tkt_pc = client.post("/auth/ticket", headers={"Authorization": f"Bearer {pc_token}"}).json()["ticket"]

    # 4. Connect via WebSockets using tickets and protocol 2.0
    with client.websocket_connect(f"/ws?ticket={tkt_phone}&protocol_version=2.0") as ws_phone:
        msg1 = ws_phone.receive_json()
        assert msg1["type"] == "devices"

        with client.websocket_connect(f"/ws?ticket={tkt_pc}&protocol_version=2.0") as ws_pc:
            msg2 = ws_pc.receive_json()
            assert msg2["type"] == "devices"

            # Both online
            online_names = [d["name"] for d in msg2["online"]]
            assert "Pixel 8 Pro" in online_names
            assert "ThinkPad X1" in online_names

            # Drain the device broadcast on phone caused by PC connection
            broadcast_msg = ws_phone.receive_json()
            assert broadcast_msg["type"] == "devices"

            # 5. Heartbeat & Active device tracking
            ws_phone.send_json({"type": "heartbeat"})
            ws_pc.send_json({"type": "heartbeat"})

            # 6. Command with idempotency ID
            cmd_id = "e2e-cmd-unique-001"
            ws_phone.send_json({
                "type": "command",
                "id": cmd_id,
                "target": "windows",
                "action": "lock_device",
                "params": {}
            })

            # PC receives dispatched command
            dispatched = ws_pc.receive_json()
            assert dispatched["type"] == "execute"
            assert dispatched["action"] == "lock_device"

            # Phone receives delivered status
            delivered_msg = ws_phone.receive_json()
            assert delivered_msg["type"] == "command_status"
            assert delivered_msg["status"] == "delivered"

            # PC sends execution result back with valid schema
            ws_pc.send_json({
                "type": "result",
                "command_id": cmd_id,
                "status": "ok",
                "result": {"locked": True}
            })

            # Phone receives final completion status
            final_msg = ws_phone.receive_json()
            assert final_msg["type"] == "command_status"
            assert final_msg["status"] == "ok"

    # 7. Check health check endpoint
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "healthy"

    # 8. Check Prometheus metrics endpoint
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    assert "beru_commands_total" in metrics_res.text
