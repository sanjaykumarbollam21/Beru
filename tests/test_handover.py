import time
import pytest
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.config import settings
from hub.handover.manager import handover_manager
from hub.skills import init_skills

@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_skills()
    monkeypatch.setattr(settings, "HEARTBEAT_TIMEOUT_SECONDS", 3600.0)
    handover_manager._records.clear()
    handover_manager._active_devices.clear()
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def register_user(client) -> tuple[dict, dict]:
    res_a = client.post("/register-first-device", json={
        "device_name": "Phone",
        "platform": "android",
        "capabilities": ["continue_on_device"]
    })
    dev_a = res_a.json()

    res_pair = client.post("/pair/start", headers={"Authorization": f"Bearer {dev_a['token']}"})
    code = res_pair.json()["code"]

    res_b = client.post("/pair/complete", json={
        "code": code,
        "device_name": "PC",
        "platform": "windows",
        "capabilities": ["continue_on_device"]
    })
    dev_b = res_b.json()
    return dev_a, dev_b

@pytest.mark.asyncio
async def test_handover_flow_and_active_device_update(client):
    phone, pc = register_user(client)
    user_id = phone["user_id"]

    # Initial active device
    handover_manager.set_active_device(user_id, phone["device_id"])
    assert handover_manager.get_active_device(user_id) == phone["device_id"]

    tkt_phone = client.post("/auth/ticket", headers={"Authorization": f"Bearer {phone['token']}"}).json()["ticket"]
    with client.websocket_connect(f"/ws?ticket={tkt_phone}") as ws_phone:
        _ = ws_phone.receive_json()

        tkt_pc = client.post("/auth/ticket", headers={"Authorization": f"Bearer {pc['token']}"}).json()["ticket"]
        with client.websocket_connect(f"/ws?ticket={tkt_pc}") as ws_pc:
            _ = ws_phone.receive_json()
            _ = ws_pc.receive_json()

            # 1. Initiate handover: continue browsing link on PC
            record = handover_manager.create_handover(
                user_id=user_id,
                from_device_id=phone["device_id"],
                to_device_id=pc["device_id"],
                context_type="link",
                custom_state={"url": "https://news.ycombinator.com"},
                summary="Continue reading Hacker News on PC"
            )

            # Dispatch request
            dispatched = await handover_manager.dispatch_handover_request(record)
            assert dispatched is True

            # PC receives handover_request
            req_msg = ws_pc.receive_json()
            assert req_msg["type"] == "handover_request"
            assert req_msg["handover_id"] == record.handover_id
            assert req_msg["context_type"] == "link"

            # 2. PC accepts handover
            ws_pc.send_json({
                "type": "handover_accept",
                "handover_id": record.handover_id
            })

            # PC receives handover_state
            state_msg = ws_pc.receive_json()
            assert state_msg["type"] == "handover_state"
            assert state_msg["state"]["url"] == "https://news.ycombinator.com"

            # Phone receives handover_done
            done_msg = ws_phone.receive_json()
            assert done_msg["type"] == "handover_done"
            assert done_msg["handover_id"] == record.handover_id

            # Active device updated to PC!
            assert handover_manager.get_active_device(user_id) == pc["device_id"]

@pytest.mark.asyncio
async def test_handover_expiration_and_decline():
    user_id = "test-user-ho"
    record = handover_manager.create_handover(
        user_id=user_id,
        from_device_id="phone-1",
        to_device_id="pc-1",
        context_type="conversation"
    )

    # Test decline
    ok, msg = handover_manager.decline_handover(record.handover_id, user_id)
    assert ok is True
    assert record.status == "declined"

    # Test expiration
    rec2 = handover_manager.create_handover(
        user_id=user_id,
        from_device_id="phone-1",
        to_device_id="pc-1",
        context_type="plan"
    )
    rec2.expires_at = time.time() - 10.0  # Expired
    assert rec2.is_expired() is True

    ok2, msg2, _ = await handover_manager.accept_handover(rec2.handover_id, user_id, "pc-1")
    assert ok2 is False
    assert "expired" in msg2

@pytest.mark.asyncio
async def test_unauthorized_user_handover_rejected():
    user_a = "user-a"
    user_b = "user-b"

    record = handover_manager.create_handover(
        user_id=user_a,
        from_device_id="phone-a",
        to_device_id="pc-a"
    )

    # User B attempts to accept User A's handover
    ok, msg, _ = await handover_manager.accept_handover(record.handover_id, user_b, "pc-b")
    assert ok is False
    assert "Unauthorized" in msg
