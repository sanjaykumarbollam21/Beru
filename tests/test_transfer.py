import os
import hashlib
from datetime import timedelta
import pytest
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.config import settings
from hub.transfer.store import transfer_store
from hub.skills import init_skills
from hub.skills.base import skill_registry

@pytest.fixture(autouse=True)
def setup_env(monkeypatch, tmp_path):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_skills()
    monkeypatch.setattr(settings, "HEARTBEAT_TIMEOUT_SECONDS", 3600.0)
    # Use temp directory for transfer storage
    storage_dir = str(tmp_path / "transfers")
    monkeypatch.setattr(settings, "TRANSFER_STORAGE_DIR", storage_dir)
    transfer_store.storage_dir = storage_dir
    os.makedirs(storage_dir, exist_ok=True)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def register_devices(client) -> tuple[dict, dict]:
    res_a = client.post("/register-first-device", json={
        "device_name": "Phone",
        "platform": "android",
        "capabilities": ["find_file", "send_file"]
    })
    dev_a = res_a.json()

    res_pair = client.post("/pair/start", headers={"Authorization": f"Bearer {dev_a['token']}"})
    code = res_pair.json()["code"]

    res_b = client.post("/pair/complete", json={
        "code": code,
        "device_name": "PC",
        "platform": "windows",
        "capabilities": ["find_file", "send_file"]
    })
    dev_b = res_b.json()
    return dev_a, dev_b

def test_chunked_upload_download_and_hash_verification(client, monkeypatch):
    phone, pc = register_devices(client)

    # Use smaller chunk size for testing: 64 bytes
    monkeypatch.setattr(settings, "TRANSFER_CHUNK_SIZE_BYTES", 64)

    file_content = b"Hello, this is a test document to be transferred across Beru devices!" * 5
    file_size = len(file_content)
    file_hash = hashlib.sha256(file_content).hexdigest()

    # 1. Start transfer
    res_start = client.post(
        "/transfer/start",
        headers={"Authorization": f"Bearer {phone['token']}"},
        json={
            "from_device": phone["device_id"],
            "to_device": pc["device_id"],
            "name": "test_document.txt",
            "size": file_size,
            "sha256": file_hash,
            "mime": "text/plain"
        }
    )
    assert res_start.status_code == 200
    start_data = res_start.json()
    transfer_id = start_data["transfer_id"]
    upload_token = start_data["upload_token"]
    chunk_size = start_data["chunk_size"]
    total_chunks = start_data["total_chunks"]

    # 2. Upload chunks with resume check
    for i in range(total_chunks):
        start = i * chunk_size
        end = min(start + chunk_size, file_size)
        chunk_bytes = file_content[start:end]

        res_chunk = client.put(
            f"/transfer/{transfer_id}/chunk/{i}",
            headers={"X-Upload-Token": upload_token},
            content=chunk_bytes
        )
        assert res_chunk.status_code == 200

    # 3. Check status
    res_status = client.get(
        f"/transfer/{transfer_id}/status",
        headers={"Authorization": f"Bearer {phone['token']}"}
    )
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["is_complete"] is True
    assert status_data["status"] == "ready"

    # 4. Download file by recipient device (PC)
    res_download = client.get(
        f"/transfer/{transfer_id}/download",
        headers={"Authorization": f"Bearer {pc['token']}"}
    )
    assert res_download.status_code == 200
    downloaded_content = res_download.content
    assert downloaded_content == file_content
    assert hashlib.sha256(downloaded_content).hexdigest() == file_hash

    # 5. Download with Range request (resumable)
    res_range = client.get(
        f"/transfer/{transfer_id}/download",
        headers={
            "Authorization": f"Bearer {pc['token']}",
            "Range": "bytes=0-49"
        }
    )
    assert res_range.status_code == 206
    assert len(res_range.content) == 50
    assert res_range.content == file_content[:50]

    # 6. Acknowledge delivery
    res_ack = client.post(
        f"/transfer/{transfer_id}/ack",
        headers={"Authorization": f"Bearer {pc['token']}"}
    )
    assert res_ack.status_code == 200

    # Stored encrypted chunks are deleted upon delivery
    rec = transfer_store.get_record(transfer_id)
    assert rec.status == "delivered"
    assert not os.path.exists(transfer_store._get_transfer_dir(transfer_id))

def test_hash_mismatch_deletes_file_and_errors(client, monkeypatch):
    phone, pc = register_devices(client)
    monkeypatch.setattr(settings, "TRANSFER_CHUNK_SIZE_BYTES", 64)

    file_content = b"Authentic original content"
    corrupt_content = b"Corrupted tampered content"
    expected_hash = hashlib.sha256(file_content).hexdigest()

    res_start = client.post(
        "/transfer/start",
        headers={"Authorization": f"Bearer {phone['token']}"},
        json={
            "from_device": phone["device_id"],
            "to_device": pc["device_id"],
            "name": "file.txt",
            "size": len(file_content),
            "sha256": expected_hash
        }
    )
    t_id = res_start.json()["transfer_id"]
    token = res_start.json()["upload_token"]

    # Upload corrupt content
    res_chunk = client.put(
        f"/transfer/{t_id}/chunk/0",
        headers={"X-Upload-Token": token},
        content=corrupt_content
    )
    assert res_chunk.status_code == 400
    assert "Hash mismatch" in res_chunk.json()["detail"]

    # Data deleted
    assert not os.path.exists(transfer_store._get_transfer_dir(t_id))

def test_size_cap_and_file_confirmation_rules(client, monkeypatch):
    phone, _ = register_devices(client)

    # Size cap rule: test with small cap
    monkeypatch.setattr(settings, "TRANSFER_MAX_FILE_SIZE_BYTES", 1000)
    res_oversize = client.post(
        "/transfer/start",
        headers={"Authorization": f"Bearer {phone['token']}"},
        json={
            "from_device": phone["device_id"],
            "to_device": "pc",
            "name": "huge_file.iso",
            "size": 5000,
            "sha256": "0" * 64
        }
    )
    assert res_oversize.status_code == 400
    assert "exceeds maximum limit" in res_oversize.json()["detail"]

    # File confirmation rules: archives/executables are 'hard', others are 'soft'
    send_skill = skill_registry.get("send_file")
    assert send_skill.get_confirmation_level({"query": "report.pdf"}) == "soft"
    assert send_skill.get_confirmation_level({"query": "setup.exe"}) == "hard"
    assert send_skill.get_confirmation_level({"query": "archive.zip"}) == "hard"

def test_offline_target_reconnect_and_expiry_sweeper(client):
    phone, pc = register_devices(client)

    file_content = b"Offline message payload"
    h = hashlib.sha256(file_content).hexdigest()

    res_start = client.post(
        "/transfer/start",
        headers={"Authorization": f"Bearer {phone['token']}"},
        json={
            "from_device": phone["device_id"],
            "to_device": pc["device_id"],
            "name": "notes.txt",
            "size": len(file_content),
            "sha256": h
        }
    )
    t_id = res_start.json()["transfer_id"]
    u_token = res_start.json()["upload_token"]

    client.put(
        f"/transfer/{t_id}/chunk/0",
        headers={"X-Upload-Token": u_token},
        content=file_content
    )

    # PC was offline; now connects via ticket and receives file_ready notification
    tkt_pc = client.post("/auth/ticket", headers={"Authorization": f"Bearer {pc['token']}"}).json()["ticket"]
    with client.websocket_connect(f"/ws?ticket={tkt_pc}") as ws_pc:
        # Initial devices list
        msg1 = ws_pc.receive_json()
        assert msg1["type"] == "devices"

        # Pending file delivered on connect
        msg_file = ws_pc.receive_json()
        assert msg_file["type"] == "file_ready"
        assert msg_file["transfer_id"] == t_id
        assert msg_file["name"] == "notes.txt"

    # Test expiry sweeper
    rec = transfer_store.get_record(t_id)
    rec.expires_at = rec.expires_at - timedelta(days=2)
    assert rec.is_expired() is True

    swept = transfer_store.sweep_expired()
    assert swept >= 1
    assert not os.path.exists(transfer_store._get_transfer_dir(t_id))
