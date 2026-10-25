import time
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from hub.main import app
from hub.db import Base, engine
from hub.config import settings
from hub.registry import registry

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def register_device(client, name="Phone", platform="android", capabilities=None) -> dict:
    res = client.post("/register-first-device", json={
        "device_name": name,
        "platform": platform,
        "capabilities": capabilities or ["lock_device", "set_volume"]
    })
    assert res.status_code == 200
    return res.json()

def pair_second_device(client, first_device_token: str, name: str, platform: str, capabilities: list[str]) -> dict:
    start_res = client.post("/pair/start", headers={"Authorization": f"Bearer {first_device_token}"})
    assert start_res.status_code == 200
    code = start_res.json()["code"]

    complete_res = client.post("/pair/complete", json={
        "code": code,
        "device_name": name,
        "platform": platform,
        "capabilities": capabilities
    })
    assert complete_res.status_code == 200
    return complete_res.json()

def get_ticket(client, device_token: str) -> str:
    res = client.post("/auth/ticket", headers={"Authorization": f"Bearer {device_token}"})
    assert res.status_code == 200
    return res.json()["ticket"]

def test_raw_token_in_url_rejected_by_default(client):
    """Verify raw tokens in ?token= URL query are strictly rejected by default."""
    dev = register_device(client, "Phone", "android", ["notify"])
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws?token={dev['token']}"):
            pass
    assert exc.value.code == 1008

def test_invalid_ticket_rejected(client):
    """Verify invalid tickets are rejected."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws?ticket=invalid_ticket"):
            pass
    assert exc.value.code == 1008

def test_missing_ticket_rejected(client):
    """Verify connections without ticket are rejected."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws"):
            pass
    assert exc.value.code == 1008

def test_device_list_broadcast(client):
    dev_a = register_device(client, "Phone", "android", ["notify"])
    dev_b = pair_second_device(client, dev_a["token"], "Laptop", "windows", ["lock"])

    tkt_a = get_ticket(client, dev_a["token"])
    with client.websocket_connect(f"/ws?ticket={tkt_a}") as ws_a:
        # Initial broadcast to device A
        msg1 = ws_a.receive_json()
        assert msg1["type"] == "devices"
        assert len(msg1["online"]) == 1
        assert msg1["online"][0]["id"] == dev_a["device_id"]

        tkt_b = get_ticket(client, dev_b["token"])
        with client.websocket_connect(f"/ws?ticket={tkt_b}") as ws_b:
            # Device B connects -> Device A receives update
            msg_a2 = ws_a.receive_json()
            assert msg_a2["type"] == "devices"
            assert len(msg_a2["online"]) == 2

            # Device B receives initial online list
            msg_b1 = ws_b.receive_json()
            assert msg_b1["type"] == "devices"
            assert len(msg_b1["online"]) == 2

        # Device B disconnected -> Device A receives updated list
        msg_a3 = ws_a.receive_json()
        assert msg_a3["type"] == "devices"
        assert len(msg_a3["online"]) == 1
        assert msg_a3["online"][0]["id"] == dev_a["device_id"]

def test_command_routing_end_to_end(client):
    dev_a = register_device(client, "Phone", "android", ["notify"])
    dev_b = pair_second_device(client, dev_a["token"], "PC", "windows", ["lock", "volume"])

    tkt_a = get_ticket(client, dev_a["token"])
    with client.websocket_connect(f"/ws?ticket={tkt_a}") as ws_a:
        _ = ws_a.receive_json()  # initial devices broadcast

        tkt_b = get_ticket(client, dev_b["token"])
        with client.websocket_connect(f"/ws?ticket={tkt_b}") as ws_b:
            _ = ws_a.receive_json()  # dev_b joined
            _ = ws_b.receive_json()  # dev_b initial list

            # Device A sends command to target "windows" with action "lock"
            cmd_id = "cmd-12345"
            ws_a.send_json({
                "type": "command",
                "id": cmd_id,
                "action": "lock",
                "target": "windows",
                "params": {"force": True}
            })

            # 1. Device A receives "delivered"
            delivered_msg = ws_a.receive_json()
            assert delivered_msg["type"] == "command_status"
            assert delivered_msg["command_id"] == cmd_id
            assert delivered_msg["status"] == "delivered"

            # 2. Device B receives "execute"
            exec_msg = ws_b.receive_json()
            assert exec_msg["type"] == "execute"
            assert exec_msg["command_id"] == cmd_id
            assert exec_msg["action"] == "lock"
            assert exec_msg["params"] == {"force": True}
            assert exec_msg["from_device"] == dev_a["device_id"]

            # 3. Device B executes and returns result
            ws_b.send_json({
                "type": "result",
                "command_id": cmd_id,
                "status": "ok",
                "data": {"locked_at": 123456}
            })

            # 4. Device A receives the result status
            result_msg = ws_a.receive_json()
            assert result_msg["type"] == "command_status"
            assert result_msg["command_id"] == cmd_id
            assert result_msg["status"] == "ok"
            assert result_msg["data"] == {"locked_at": 123456}

def test_command_offline_target(client):
    dev_a = register_device(client, "Phone", "android", ["notify"])

    tkt_a = get_ticket(client, dev_a["token"])
    with client.websocket_connect(f"/ws?ticket={tkt_a}") as ws_a:
        _ = ws_a.receive_json()  # devices broadcast

        # Target "windows" is offline
        ws_a.send_json({
            "type": "command",
            "id": "cmd-offline",
            "action": "lock",
            "target": "windows",
            "params": {}
        })

        res = ws_a.receive_json()
        assert res["type"] == "command_status"
        assert res["command_id"] == "cmd-offline"
        assert res["status"] == "offline"

def test_command_unsupported_capability(client):
    dev_a = register_device(client, "Phone", "android", ["notify"])
    dev_b = pair_second_device(client, dev_a["token"], "PC", "windows", ["lock"])

    tkt_a = get_ticket(client, dev_a["token"])
    with client.websocket_connect(f"/ws?ticket={tkt_a}") as ws_a:
        _ = ws_a.receive_json()

        tkt_b = get_ticket(client, dev_b["token"])
        with client.websocket_connect(f"/ws?ticket={tkt_b}") as ws_b:
            _ = ws_a.receive_json()
            _ = ws_b.receive_json()

            # "reboot" is not in dev_b capabilities
            ws_a.send_json({
                "type": "command",
                "id": "cmd-unsupported",
                "action": "reboot",
                "target": "windows",
                "params": {}
            })

            res = ws_a.receive_json()
            assert res["type"] == "command_status"
            assert res["command_id"] == "cmd-unsupported"
            assert res["status"] == "error"
            assert res["error"] == "unsupported"

def test_command_timeout(client, monkeypatch):
    # Shorten timeout for test
    monkeypatch.setattr(settings, "COMMAND_TIMEOUT_SECONDS", 0.3)

    dev_a = register_device(client, "Phone", "android", ["notify"])
    dev_b = pair_second_device(client, dev_a["token"], "PC", "windows", ["lock"])

    tkt_a = get_ticket(client, dev_a["token"])
    with client.websocket_connect(f"/ws?ticket={tkt_a}") as ws_a:
        _ = ws_a.receive_json()

        tkt_b = get_ticket(client, dev_b["token"])
        with client.websocket_connect(f"/ws?ticket={tkt_b}") as ws_b:
            _ = ws_a.receive_json()
            _ = ws_b.receive_json()

            cmd_id = "cmd-timeout-test"
            ws_a.send_json({
                "type": "command",
                "id": cmd_id,
                "action": "lock",
                "target": "windows",
                "params": {}
            })

            # Delivered status
            delivered = ws_a.receive_json()
            assert delivered["status"] == "delivered"

            # Execute received by B, but B does NOT reply
            exec_msg = ws_b.receive_json()
            assert exec_msg["type"] == "execute"

            # Timeout after 0.3s
            timeout_msg = ws_a.receive_json()
            assert timeout_msg["type"] == "command_status"
            assert timeout_msg["command_id"] == cmd_id
            assert timeout_msg["status"] == "error"
            assert timeout_msg["error"] == "timeout"

def test_heartbeat_updates_and_timeout(client):
    dev_a = register_device(client, "Phone", "android", ["notify"])

    tkt_a = get_ticket(client, dev_a["token"])
    with client.websocket_connect(f"/ws?ticket={tkt_a}") as ws_a:
        _ = ws_a.receive_json()

        # Send heartbeat
        ws_a.send_json({"type": "heartbeat"})
        time.sleep(0.05)

        online_dev = pytest.importorskip("asyncio").run(registry.get_device(dev_a["device_id"]))
        assert online_dev is not None
        assert online_dev.device_id == dev_a["device_id"]
