"""
Beru Phase 3 End-to-End Simulation: Voice Input and Output
Demonstrates:
  1. Bootstrapping user, registering Phone (Android) and PC (Windows).
  2. Obtaining single-use tickets for WebSocket authentication.
  3. PC connects to /ws?ticket=... and Phone connects to /voice?ticket=...
  4. Phone initiates voice session, sends audio bytes, triggers STT pipeline.
  5. Hub strips wake phrase "Hey Beru", resolves intent to set volume on PC.
  6. PC executes command and reports ok.
  7. Voice client receives thinking, final_transcript, spoken reply, and done.
"""
import math
import struct
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.config import settings
from hub.skills import init_skills
from hub.voice.stt import stt_orchestrator, MockSTTProvider
from hub.voice.tts import tts_orchestrator, MockTTSProvider

def generate_pcm_sine(duration_sec: float = 0.3, sample_rate: int = 16000, freq: float = 440.0) -> bytes:
    samples = []
    num_samples = int(duration_sec * sample_rate)
    for i in range(num_samples):
        val = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
        samples.append(struct.pack("<h", val))
    return b"".join(samples)

def print_step(title: str):
    print("\n" + "=" * 68)
    print(f"[STEP] {title}")
    print("=" * 68)

def run_phase3_demo():
    print("=" * 68)
    print("      BERU PHASE 3: VOICE INPUT AND OUTPUT END-TO-END DEMO")
    print("=" * 68)

    init_skills()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    settings.HEARTBEAT_TIMEOUT_SECONDS = 3600.0

    mock_stt = MockSTTProvider()
    mock_tts = MockTTSProvider()
    stt_orchestrator.mock_provider = mock_stt
    tts_orchestrator.mock_provider = mock_tts

    with TestClient(app) as client:
        print_step("1. Initialize and Pair Phone (Android) and PC (Windows)")
        res_phone = client.post("/register-first-device", json={
            "device_name": "Pixel 8 Pro",
            "platform": "android",
            "capabilities": ["lock_device", "set_volume", "open_app"]
        })
        phone = res_phone.json()
        phone_token = phone["token"]
        phone_id = phone["device_id"]
        print(f"-> Phone registered: Pixel 8 Pro (ID: {phone_id})")

        res_code = client.post("/pair/start", headers={"Authorization": f"Bearer {phone_token}"})
        code = res_code.json()["code"]

        res_pc = client.post("/pair/complete", json={
            "code": code,
            "device_name": "ThinkPad PC",
            "platform": "windows",
            "capabilities": ["lock", "volume", "open_app"]
        })
        pc = res_pc.json()
        pc_token = pc["token"]
        pc_id = pc["device_id"]
        print(f"-> PC paired: ThinkPad PC (ID: {pc_id})")

        print_step("2. Request Single-Use WebSocket Tickets")
        tkt_pc = client.post("/auth/ticket", headers={"Authorization": f"Bearer {pc_token}"}).json()["ticket"]
        tkt_phone = client.post("/auth/ticket", headers={"Authorization": f"Bearer {phone_token}"}).json()["ticket"]
        print(f"-> PC ticket:    {tkt_pc[:15]}... (TTL: 30s)")
        print(f"-> Phone ticket: {tkt_phone[:15]}... (TTL: 30s)")

        print_step("3. Connect PC to /ws and Phone to /voice")
        with client.websocket_connect(f"/ws?ticket={tkt_pc}") as ws_pc:
            _ = ws_pc.receive_json()
            print("-> PC connected to command WebSocket gateway.")

            with client.websocket_connect(f"/voice?ticket={tkt_phone}") as ws_voice:
                print("-> Phone connected to voice streaming WebSocket gateway.")

                print_step("4. Voice Turn: Spoken Command with Wake Word")
                spoken_utterance = "Hey Beru, set volume to 50 on my PC"
                stt_orchestrator.mock_provider.set_transcript(spoken_utterance)
                print(f"-> User speaks to phone microphone: '{spoken_utterance}'")

                # Send start event
                ws_voice.send_json({"type": "voice_start", "mode": "wake_word", "tts": "client"})
                msg_listening = ws_voice.receive_json()
                assert msg_listening["type"] == "listening"
                print("-> Hub acknowledges: state=LISTENING")

                # Stream audio and conclude
                audio_bytes = generate_pcm_sine(duration_sec=0.25)
                ws_voice.send_bytes(audio_bytes)
                ws_voice.send_json({"type": "voice_end"})

                msg_thinking = ws_voice.receive_json()
                assert msg_thinking["type"] == "thinking"
                print("-> Hub acknowledges: state=THINKING (transcribing speech)")

                msg_transcript = ws_voice.receive_json()
                assert msg_transcript["type"] == "final_transcript"
                print(f"-> Transcribed text: '{msg_transcript['text']}'")

                print_step("5. Intent Resolution and Command Dispatch to PC")
                pc_exec = ws_pc.receive_json()
                assert pc_exec["type"] == "execute"
                assert pc_exec["action"] == "volume"
                assert pc_exec["params"]["level"] == 50
                print(f"-> PC received execution request: action='{pc_exec['action']}', level={pc_exec['params']['level']}")

                # PC executes and returns result
                ws_pc.send_json({
                    "type": "result",
                    "command_id": pc_exec["command_id"],
                    "status": "ok",
                    "data": {"volume": 50}
                })
                print("-> PC simulated volume change to 50% and returned status 'ok'.")

                print_step("6. Voice Client Receives Spoken Feedback")
                msg_reply = ws_voice.receive_json()
                assert msg_reply["type"] == "reply"
                assert msg_reply["speak"] is True
                print(f"-> Spoken reply received: '{msg_reply['text']}'")

                msg_done = ws_voice.receive_json()
                assert msg_done["type"] == "done"
                print("-> Voice turn complete: state=DONE")

    print("\n" + "=" * 68)
    print("SUCCESS: Phase 3 end-to-end voice I/O turn simulation verified!")
    print("=" * 68)

if __name__ == "__main__":
    run_phase3_demo()
