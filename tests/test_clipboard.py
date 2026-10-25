import pytest
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.config import settings
from hub.clipboard.sync import clipboard_sync_manager
from hub.skills import init_skills

@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_skills()
    monkeypatch.setattr(settings, "HEARTBEAT_TIMEOUT_SECONDS", 3600.0)
    clipboard_sync_manager._states.clear()
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
        "capabilities": ["copy_to_device", "paste_from_device"]
    })
    dev_a = res_a.json()

    res_pair = client.post("/pair/start", headers={"Authorization": f"Bearer {dev_a['token']}"})
    code = res_pair.json()["code"]

    res_b = client.post("/pair/complete", json={
        "code": code,
        "device_name": "PC",
        "platform": "windows",
        "capabilities": ["copy_to_device", "paste_from_device"]
    })
    dev_b = res_b.json()
    return dev_a, dev_b

def test_clipboard_push_and_loop_prevention(client):
    phone, pc = register_user(client)

    tkt_phone = client.post("/auth/ticket", headers={"Authorization": f"Bearer {phone['token']}"}).json()["ticket"]
    with client.websocket_connect(f"/ws?ticket={tkt_phone}") as ws_phone:
        _ = ws_phone.receive_json()

        tkt_pc = client.post("/auth/ticket", headers={"Authorization": f"Bearer {pc['token']}"}).json()["ticket"]
        with client.websocket_connect(f"/ws?ticket={tkt_pc}") as ws_pc:
            _ = ws_phone.receive_json()
            _ = ws_pc.receive_json()

            # Phone sends clipboard update
            clip_text = "https://github.com/google/beru"
            ws_phone.send_json({
                "type": "clipboard_update",
                "text": clip_text,
                "origin_device": phone["device_id"]
            })

            # PC receives clipboard_push
            pc_msg = ws_pc.receive_json()
            assert pc_msg["type"] == "clipboard_push"
            assert pc_msg["text"] == clip_text
            assert pc_msg["from_device"] == phone["device_id"]

            # Loop prevention: Phone must NOT receive duplicate push
            # Duplicate within 5s is rejected
            ok, err, _ = clipboard_sync_manager.update_clipboard(
                user_id=phone["user_id"],
                origin_device=phone["device_id"],
                text=clip_text
            )
            assert ok is False
            assert "Duplicate clip within 5s" in err

def test_clipboard_oversize_rejected():
    user_id = "test-user-clip"
    oversized_text = "A" * (settings.CLIPBOARD_MAX_SIZE_BYTES + 500)

    ok, err, push_msg = clipboard_sync_manager.update_clipboard(
        user_id=user_id,
        origin_device="phone",
        text=oversized_text
    )
    assert ok is False
    assert "limit" in err

def test_clipboard_isolation_between_users():
    user_a = "user-alpha"
    user_b = "user-beta"

    clipboard_sync_manager.update_clipboard(user_a, "phone-a", "Secret A")
    clipboard_sync_manager.update_clipboard(user_b, "phone-b", "Secret B")

    clip_a = clipboard_sync_manager.get_latest_clip(user_a)
    clip_b = clipboard_sync_manager.get_latest_clip(user_b)

    assert clip_a["text"] == "Secret A"
    assert clip_b["text"] == "Secret B"
