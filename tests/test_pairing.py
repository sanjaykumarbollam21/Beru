import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from hub.main import app
from hub.db import Base, engine, SessionLocal, utcnow, PairingCode, Device
from hub.auth import hash_token

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

def test_register_first_device_success(client):
    payload = {
        "device_name": "My PC",
        "platform": "windows",
        "capabilities": ["lock", "open_browser"]
    }
    response = client.post("/register-first-device", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "device_id" in data
    assert "token" in data
    raw_token = data["token"]

    # Verify device exists in DB and token is hashed
    with SessionLocal() as db:
        dev = db.query(Device).filter(Device.id == data["device_id"]).first()
        assert dev is not None
        assert dev.token_hash == hash_token(raw_token)
        assert dev.token_hash != raw_token
        assert dev.platform == "windows"
        assert "lock" in dev.capabilities

def test_register_first_device_once_per_user(client):
    payload = {
        "device_name": "PC 1",
        "platform": "windows",
        "capabilities": []
    }
    res1 = client.post("/register-first-device", json=payload)
    assert res1.status_code == 200
    user_id = res1.json()["user_id"]

    # Try registering another first device with same user_id
    payload2 = {
        "device_name": "PC 2",
        "platform": "windows",
        "capabilities": [],
        "user_id": user_id
    }
    res2 = client.post("/register-first-device", json=payload2)
    assert res2.status_code == 400
    assert "already been registered" in res2.json()["detail"]

def test_pairing_flow_success(client):
    # 1. Bootstrap Device A (Phone)
    res_a = client.post("/register-first-device", json={
        "device_name": "Android Phone",
        "platform": "android",
        "capabilities": ["notify"]
    })
    assert res_a.status_code == 200
    token_a = res_a.json()["token"]
    user_id = res_a.json()["user_id"]

    # 2. Device A starts pairing
    res_pair_start = client.post(
        "/pair/start",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert res_pair_start.status_code == 200
    pair_data = res_pair_start.json()
    code = pair_data["code"]
    assert len(code) == 6
    assert "qr_payload" in pair_data
    assert pair_data["qr_image"].startswith("data:image/png;base64,")

    # 3. Device B completes pairing with code
    res_pair_complete = client.post("/pair/complete", json={
        "code": code,
        "device_name": "Windows PC",
        "platform": "windows",
        "capabilities": ["lock", "volume"]
    })
    assert res_pair_complete.status_code == 200
    dev_b_data = res_pair_complete.json()
    assert dev_b_data["user_id"] == user_id
    assert "token" in dev_b_data
    token_b = dev_b_data["token"]

    # Verify device B in db
    with SessionLocal() as db:
        dev_b = db.query(Device).filter(Device.id == dev_b_data["device_id"]).first()
        assert dev_b is not None
        assert dev_b.user_id == user_id
        assert dev_b.token_hash == hash_token(token_b)

def test_pairing_code_cannot_be_reused(client):
    res_a = client.post("/register-first-device", json={
        "device_name": "Device A",
        "platform": "windows",
        "capabilities": []
    })
    token_a = res_a.json()["token"]

    res_pair_start = client.post(
        "/pair/start",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    code = res_pair_start.json()["code"]

    # Complete once
    res1 = client.post("/pair/complete", json={
        "code": code,
        "device_name": "Device B",
        "platform": "android",
        "capabilities": []
    })
    assert res1.status_code == 200

    # Complete again with same code
    res2 = client.post("/pair/complete", json={
        "code": code,
        "device_name": "Device C",
        "platform": "android",
        "capabilities": []
    })
    assert res2.status_code == 400
    assert "already been used" in res2.json()["detail"]

def test_expired_pairing_code_rejected(client):
    res_a = client.post("/register-first-device", json={
        "device_name": "Device A",
        "platform": "windows",
        "capabilities": []
    })
    token_a = res_a.json()["token"]

    res_pair_start = client.post(
        "/pair/start",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    code = res_pair_start.json()["code"]

    # Manually expire the code in the DB
    with SessionLocal() as db:
        record = db.query(PairingCode).filter(PairingCode.code == code).first()
        record.expires_at = utcnow() - timedelta(seconds=10)
        db.commit()

    res = client.post("/pair/complete", json={
        "code": code,
        "device_name": "Device B",
        "platform": "android",
        "capabilities": []
    })
    assert res.status_code == 400
    assert "expired" in res.json()["detail"]

def test_invalid_pairing_code_rejected(client):
    res = client.post("/pair/complete", json={
        "code": "NONEXISTENT",
        "device_name": "Device B",
        "platform": "android",
        "capabilities": []
    })
    assert res.status_code == 400
    assert "Invalid pairing code" in res.json()["detail"]
