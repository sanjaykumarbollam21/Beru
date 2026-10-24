import pytest
import numpy as np
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from hub.main import app
from hub.db import Base, engine
from hub.config import settings
from hub.skills import init_skills
from hub.voice.session import classify_spoken_confirmation, voice_session_manager
from hub.voice.stt import stt_orchestrator, MockSTTProvider
from hub.voice.tts import tts_orchestrator, MockTTSProvider

def generate_pcm_sine(freq=440.0, duration_sec=0.1, sample_rate=16000, amplitude=0.5) -> bytes:
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    return samples.tobytes()

@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_skills()
    monkeypatch.setattr(settings, "HEARTBEAT_TIMEOUT_SECONDS", 3600.0)

    mock_stt = MockSTTProvider()
    mock_tts = MockTTSProvider()
    stt_orchestrator.mock_provider = mock_stt
    tts_orchestrator.mock_provider = mock_tts
    yield
    stt_orchestrator.mock_provider = None
    tts_orchestrator.mock_provider = None
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def register_user_phone_and_pc(client) -> tuple[dict, dict]:
    res_phone = client.post("/register-first-device", json={
        "device_name": "Pixel 8",
        "platform": "android",
        "capabilities": ["notify", "set_alarm", "flashlight", "send_message"]
    })
    phone = res_phone.json()

    res_pair = client.post("/pair/start", headers={"Authorization": f"Bearer {phone['token']}"})
    code = res_pair.json()["code"]

    res_pc = client.post("/pair/complete", json={
        "code": code,
        "device_name": "PC",
        "platform": "windows",
        "capabilities": ["lock", "volume", "open_app"]
    })
    pc = res_pc.json()
    return phone, pc

def test_classify_spoken_confirmation():
    assert classify_spoken_confirmation("yes") is True
    assert classify_spoken_confirmation("Yeah, go ahead") is True
    assert classify_spoken_confirmation("Confirm please") is True
    assert classify_spoken_confirmation("sure") is True

    assert classify_spoken_confirmation("no") is False
    assert classify_spoken_confirmation("cancel") is False
    assert classify_spoken_confirmation("stop that") is False
    assert classify_spoken_confirmation("nevermind") is False

    assert classify_spoken_confirmation("what time is it") is None
    assert classify_spoken_confirmation("maybe tomorrow") is None

def test_voice_ws_invalid_token_rejected(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/voice?token=invalid_token") as ws:
            pass
    assert exc.value.code == 1008

def test_voice_ws_complete_turn_flow(client):
    phone, pc = register_user_phone_and_pc(client)
    stt_orchestrator.mock_provider.set_transcript("Hey Beru, set volume to 50 on my PC")

    # Connect PC to regular /ws so it can execute volume if targeted
    with client.websocket_connect(f"/ws?token={pc['token']}") as ws_pc:
        _ = ws_pc.receive_json()

        # Phone connects to /voice
        with client.websocket_connect(f"/voice?token={phone['token']}") as ws_voice:
            # 1. Start session
            ws_voice.send_json({"type": "voice_start", "mode": "wake_word", "tts": "client"})
            msg_listening = ws_voice.receive_json()
            assert msg_listening["type"] == "listening"

            # 2. Feed audio chunk and end session
            ws_voice.send_bytes(generate_pcm_sine(duration_sec=0.2))
            ws_voice.send_json({"type": "voice_end"})

            # 3. Receive thinking, final_transcript, and reply
            msg_thinking = ws_voice.receive_json()
            assert msg_thinking["type"] == "thinking"

            msg_transcript = ws_voice.receive_json()
            assert msg_transcript["type"] == "final_transcript"
            assert msg_transcript["text"] == "Hey Beru, set volume to 50 on my PC"

            # PC will receive execute for set_volume
            pc_exec = ws_pc.receive_json()
            assert pc_exec["type"] == "execute"
            assert pc_exec["action"] == "volume"
            assert pc_exec["params"]["level"] == 50

            # PC replies with ok result
            ws_pc.send_json({
                "type": "result",
                "command_id": pc_exec["command_id"],
                "status": "ok",
                "data": {"volume": 50}
            })

            # Voice client receives reply
            msg_reply = ws_voice.receive_json()
            assert msg_reply["type"] == "reply"
            assert msg_reply["speak"] is True
            assert "Executed set_volume" in msg_reply["text"]

            msg_done = ws_voice.receive_json()
            assert msg_done["type"] == "done"

def test_voice_ws_spoken_confirmation_flow(client):
    phone, pc = register_user_phone_and_pc(client)

    with client.websocket_connect(f"/ws?token={pc['token']}") as ws_pc:
        _ = ws_pc.receive_json()

        with client.websocket_connect(f"/voice?token={phone['token']}") as ws_voice:
            # Turn 1: User says "lock my pc"
            stt_orchestrator.mock_provider.set_transcript("lock my pc")

            ws_voice.send_json({"type": "voice_start", "mode": "wake_word", "tts": "client"})
            _ = ws_voice.receive_json()  # listening

            ws_voice.send_bytes(generate_pcm_sine(duration_sec=0.2))
            ws_voice.send_json({"type": "voice_end"})

            _ = ws_voice.receive_json()  # thinking
            _ = ws_voice.receive_json()  # final_transcript

            # Hub replies with confirmation prompt and re-opens listening
            reply_conf = ws_voice.receive_json()
            assert reply_conf["type"] == "reply"
            assert reply_conf["expect_reply"] is True
            assert reply_conf["action"] == "confirm"
            assert "Lock windows screen" in reply_conf["text"]

            msg_listen_again = ws_voice.receive_json()
            assert msg_listen_again["type"] == "listening"

            # Turn 2: User says "yes" to confirm
            stt_orchestrator.mock_provider.set_transcript("yes please")
            ws_voice.send_bytes(generate_pcm_sine(duration_sec=0.2))
            ws_voice.send_json({"type": "voice_end"})

            _ = ws_voice.receive_json()  # thinking
            _ = ws_voice.receive_json()  # final_transcript

            # PC receives execute command for lock
            pc_exec = ws_pc.receive_json()
            assert pc_exec["type"] == "execute"
            assert pc_exec["action"] == "lock"

            ws_pc.send_json({
                "type": "result",
                "command_id": pc_exec["command_id"],
                "status": "ok",
                "data": {"locked": True}
            })

            # Phone receives confirmed reply
            final_reply = ws_voice.receive_json()
            assert final_reply["type"] == "reply"
            assert "Confirmed" in final_reply["text"]
            assert final_reply["expect_reply"] is False

            done_msg = ws_voice.receive_json()
            assert done_msg["type"] == "done"
