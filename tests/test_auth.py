import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from hub.main import app
from hub.db import Base, engine, SessionLocal, Device
from hub.config import settings
from hub.security.tickets import ticket_manager

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

def register_device(client, name="Test Phone", platform="android", capabilities=None):
    res = client.post("/register-first-device", json={
        "device_name": name,
        "platform": platform,
        "capabilities": capabilities or ["lock_device"]
    })
    assert res.status_code == 200
    return res.json()

def test_ticket_request_success(client):
    """POST /auth/ticket issues a short-lived single-use ticket."""
    dev = register_device(client)
    res = client.post("/auth/ticket", headers={"Authorization": f"Bearer {dev['token']}"})
    assert res.status_code == 200
    data = res.json()
    assert "ticket" in data
    assert data["ticket"].startswith("tkt_")
    assert data["expires_in"] == settings.WS_TICKET_EXPIRE_SECONDS

def test_ticket_request_invalid_token(client):
    """POST /auth/ticket with invalid Bearer token returns 401."""
    res = client.post("/auth/ticket", headers={"Authorization": "Bearer invalid_token_123"})
    assert res.status_code == 401

def test_ticket_single_use(client):
    """Ticket can only be used once to establish a WebSocket connection."""
    dev = register_device(client)
    res = client.post("/auth/ticket", headers={"Authorization": f"Bearer {dev['token']}"})
    ticket = res.json()["ticket"]

    # 1st use succeeds
    with client.websocket_connect(f"/ws?ticket={ticket}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "devices"

    # 2nd use fails with policy violation (1008)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws?ticket={ticket}"):
            pass
    assert exc.value.code == 1008

def test_ticket_expiry(client):
    """Expired tickets are rejected with 1008."""
    dev = register_device(client)
    expired_ticket = ticket_manager.create_ticket(
        device_id=dev["device_id"],
        user_id=dev["user_id"],
        ttl_seconds=-5  # expired
    )
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws?ticket={expired_ticket}"):
            pass
    assert exc.value.code == 1008

def test_raw_token_in_url_rejected(client):
    """Raw device tokens in /ws?token= must be rejected by default to prevent URL logging leaks."""
    dev = register_device(client)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws?token={dev['token']}"):
            pass
    assert exc.value.code == 1008

def test_raw_token_in_voice_url_rejected(client):
    """Raw device tokens in /voice?token= must be rejected by default."""
    dev = register_device(client)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/voice?token={dev['token']}"):
            pass
    assert exc.value.code == 1008

def test_ticket_revoked_device_rejected(client):
    """Tickets for a revoked device cannot connect."""
    dev = register_device(client)
    res = client.post("/auth/ticket", headers={"Authorization": f"Bearer {dev['token']}"})
    ticket = res.json()["ticket"]

    # Revoke device
    with SessionLocal() as db:
        d = db.query(Device).filter(Device.id == dev["device_id"]).first()
        d.is_revoked = True
        db.commit()

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws?ticket={ticket}"):
            pass
    assert exc.value.code == 1008
