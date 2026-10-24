import time
import pytest
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.config import settings
from hub.wake.models import WakeClaim
from hub.wake.scoring import wake_scorer
from hub.wake.arbiter import wake_arbiter
from hub.personalization.store import preference_store

@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "HEARTBEAT_TIMEOUT_SECONDS", 3600.0)
    monkeypatch.setattr(settings, "ARBITRATION_WINDOW_MS", 50)  # fast 50ms window for tests
    wake_arbiter._pending_claims.clear()
    wake_arbiter._cooldown_timestamps.clear()
    wake_arbiter._recent_winners.clear()
    wake_arbiter._recent_decisions.clear()
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def register_user(client) -> tuple[dict, dict]:
    res_a = client.post("/register-first-device", json={
        "device_name": "Pixel Phone",
        "platform": "android"
    })
    phone = res_a.json()

    res_pair = client.post("/pair/start", headers={"Authorization": f"Bearer {phone['token']}"})
    code = res_pair.json()["code"]

    res_b = client.post("/pair/complete", json={
        "code": code,
        "device_name": "ThinkPad PC",
        "platform": "windows"
    })
    pc = res_b.json()
    return phone, pc

def test_two_simultaneous_claims_higher_score_wins(client):
    phone, pc = register_user(client)

    with client.websocket_connect(f"/ws?token={phone['token']}") as ws_phone:
        _ = ws_phone.receive_json()

        with client.websocket_connect(f"/ws?token={pc['token']}") as ws_pc:
            _ = ws_phone.receive_json()
            _ = ws_pc.receive_json()

            # Phone claim: lower signal & detector score
            phone_claim_id = "claim-phone-1"
            ws_phone.send_json({
                "type": "wake_claim",
                "claim_id": phone_claim_id,
                "detector_score": 0.60,
                "signal_level": 0.30,
                "screen_on": False,
                "in_use": False,
                "charging": False
            })

            # PC claim: higher signal & detector score
            pc_claim_id = "claim-pc-1"
            ws_pc.send_json({
                "type": "wake_claim",
                "claim_id": pc_claim_id,
                "detector_score": 0.90,
                "signal_level": 0.85,
                "screen_on": True,
                "in_use": True,
                "charging": True
            })

            # Wait for arbitration window to resolve
            msg_phone = ws_phone.receive_json()
            msg_pc = ws_pc.receive_json()

            # Phone loses, PC wins!
            assert msg_phone["type"] == "wake_lose"
            assert msg_phone["claim_id"] == phone_claim_id

            assert msg_pc["type"] == "wake_win"
            assert msg_pc["claim_id"] == pc_claim_id

def test_claim_window_and_cooldown_drops_late_claims(client):
    phone, pc = register_user(client)

    with client.websocket_connect(f"/ws?token={phone['token']}") as ws_phone:
        _ = ws_phone.receive_json()

        with client.websocket_connect(f"/ws?token={pc['token']}") as ws_pc:
            _ = ws_phone.receive_json()
            _ = ws_pc.receive_json()

            # 1. First claim wins
            ws_phone.send_json({
                "type": "wake_claim",
                "claim_id": "phone-win-1",
                "detector_score": 0.90,
                "signal_level": 0.80
            })

            msg = ws_phone.receive_json()
            assert msg["type"] == "wake_win"

            # 2. Immediate late claim within cooldown is dropped and receives wake_lose
            ws_pc.send_json({
                "type": "wake_claim",
                "claim_id": "pc-late-1",
                "detector_score": 0.95,
                "signal_level": 0.90
            })

            late_msg = ws_pc.receive_json()
            assert late_msg["type"] == "wake_lose"
            assert late_msg["claim_id"] == "pc-late-1"

def test_hysteresis_keeps_recent_winner_stable():
    claim_a = WakeClaim(device_id="dev-a", user_id="u1", detector_score=0.75, signal_level=0.50)
    claim_b = WakeClaim(device_id="dev-b", user_id="u1", detector_score=0.78, signal_level=0.55)

    # Without hysteresis, dev-b has slightly higher score
    winner1, _, scores1 = wake_scorer.select_winner(
        claims=[claim_a, claim_b],
        device_platforms={"dev-a": "android", "dev-b": "windows"},
        last_winner_device_id=None
    )
    assert winner1.device_id == "dev-b"

    # With hysteresis: dev-a was recent winner, gets +0.10 bonus, overcoming dev-b!
    winner2, _, scores2 = wake_scorer.select_winner(
        claims=[claim_a, claim_b],
        device_platforms={"dev-a": "android", "dev-b": "windows"},
        last_winner_device_id="dev-a"
    )
    assert winner2.device_id == "dev-a"
    assert scores2["dev-a"] > scores2["dev-b"]

def test_low_score_solo_claim_rejected():
    # detector_score below minimum threshold (0.30)
    claim = WakeClaim(device_id="dev-a", user_id="u1", detector_score=0.20, signal_level=0.50)
    winner, _, scores = wake_scorer.select_winner(
        claims=[claim],
        device_platforms={"dev-a": "android"}
    )
    assert winner is None
    assert scores["dev-a"] == 0.0

def test_pinned_preferred_device_always_wins(client):
    phone, pc = register_user(client)
    user_id = phone["user_id"]

    # Pin PC as preferred wake device in user preferences
    preference_store.set_preference(user_id, "preferred_wake_device", pc["device_id"])

    with client.websocket_connect(f"/ws?token={phone['token']}") as ws_phone:
        _ = ws_phone.receive_json()

        with client.websocket_connect(f"/ws?token={pc['token']}") as ws_pc:
            _ = ws_phone.receive_json()
            _ = ws_pc.receive_json()

            # Phone has higher detector score and signal, but PC is pinned!
            ws_phone.send_json({
                "type": "wake_claim",
                "claim_id": "phone-c1",
                "detector_score": 0.95,
                "signal_level": 0.90
            })
            ws_pc.send_json({
                "type": "wake_claim",
                "claim_id": "pc-c1",
                "detector_score": 0.65,
                "signal_level": 0.50
            })

            msg_phone = ws_phone.receive_json()
            msg_pc = ws_pc.receive_json()

            assert msg_phone["type"] == "wake_lose"
            assert msg_pc["type"] == "wake_win"

def test_wake_failed_promotes_runner_up(client):
    phone, pc = register_user(client)

    with client.websocket_connect(f"/ws?token={phone['token']}") as ws_phone:
        _ = ws_phone.receive_json()

        with client.websocket_connect(f"/ws?token={pc['token']}") as ws_pc:
            _ = ws_phone.receive_json()
            _ = ws_pc.receive_json()

            # PC wins, Phone is runner-up
            ws_phone.send_json({
                "type": "wake_claim",
                "claim_id": "phone-claim",
                "detector_score": 0.70,
                "signal_level": 0.60
            })
            ws_pc.send_json({
                "type": "wake_claim",
                "claim_id": "pc-claim",
                "detector_score": 0.90,
                "signal_level": 0.85
            })

            _ = ws_phone.receive_json() # wake_lose
            win_pc = ws_pc.receive_json()
            assert win_pc["type"] == "wake_win"

            # PC fails to open /voice, sends wake_failed
            ws_pc.send_json({
                "type": "wake_failed",
                "claim_id": "pc-claim"
            })

            # Runner-up (Phone) receives wake_win!
            promoted_msg = ws_phone.receive_json()
            assert promoted_msg["type"] == "wake_win"
            assert promoted_msg["claim_id"] == "phone-claim"
