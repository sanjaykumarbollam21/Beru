import pytest
import time
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.skills import init_skills
from hub.dialog import dialog_manager
from hub.confirm import confirmation_gate
from hub.llm import llm_orchestrator, MockLLMProvider, LLMProvider
from hub.router import command_router
from hub.skills.base import skill_registry

@pytest.fixture(autouse=True)
def setup_all():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_skills()
    llm_orchestrator.mock_provider = None
    yield
    llm_orchestrator.mock_provider = None
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def register_user_and_phone(client) -> dict:
    res = client.post("/register-first-device", json={
        "device_name": "Pixel",
        "platform": "android",
        "capabilities": ["notify", "set_alarm", "send_message", "flashlight"]
    })
    return res.json()

def pair_pc(client, token: str) -> dict:
    pair_res = client.post("/pair/start", headers={"Authorization": f"Bearer {token}"})
    code = pair_res.json()["code"]
    res = client.post("/pair/complete", json={
        "code": code,
        "device_name": "PC",
        "platform": "windows",
        "capabilities": ["lock", "volume", "open_app"]
    })
    return res.json()

@pytest.mark.asyncio
async def test_slot_filling_and_expiration():
    user_id = "test-user-dialog-1"

    # Step 1: Send incomplete command: "send a message"
    turn1 = await dialog_manager.process_user_text(user_id=user_id, text="send a message")
    assert turn1.type == "clarify"
    assert "recipient" in turn1.missing_slots
    assert "Who would you like to send the message to?" in turn1.question

    # Step 2: User responds with recipient: "Alice saying I am on my way"
    turn2 = await dialog_manager.process_user_text(user_id=user_id, text="Alice saying I am on my way")
    assert turn2.type == "ready"
    assert turn2.intent.skill.name == "send_message"
    assert turn2.intent.params["recipient"] == "Alice"
    assert turn2.intent.params["message"] == "I am on my way"

    # Test Expiration
    turn3 = await dialog_manager.process_user_text(user_id="test-user-exp", text="send a message")
    assert turn3.type == "clarify"
    state = dialog_manager.get_state("test-user-exp")
    state.pending_since = time.time() - 70.0  # Expire 60s timeout

    # Next text should not fill expired pending, but be parsed afresh
    turn4 = await dialog_manager.process_user_text(user_id="test-user-exp", text="set volume to 50")
    assert turn4.type == "ready"
    assert turn4.intent.skill.name == "set_volume"
    assert turn4.intent.params["level"] == 50

@pytest.mark.asyncio
async def test_confirmation_gate_workflow():
    user_id = "user-confirm-test"
    skill = skill_registry.get("send_message")
    intent = pytest.importorskip("hub.intent.resolver").ResolvedIntent(
        skill=skill,
        params={"recipient": "Bob", "message": "Hi"},
        target_platform="android",
        target_device="phone",
        confidence=0.95,
        requires_confirmation=True,
        confirmation_level="hard"
    )

    conf = confirmation_gate.create_confirmation(
        user_id=user_id,
        sender_device_id="phone-1",
        intent=intent,
        timeout=0.2
    )
    assert conf.status == "pending"

    # Expire confirmation
    time.sleep(0.25)
    ok, rec, msg = confirmation_gate.confirm(conf.id, user_id)
    assert ok is False
    assert "expired" in msg

    # New confirmation and successful confirm
    conf2 = confirmation_gate.create_confirmation(
        user_id=user_id,
        sender_device_id="phone-1",
        intent=intent,
        timeout=10.0
    )
    ok, rec, msg = confirmation_gate.confirm(conf2.id, user_id)
    assert ok is True
    assert rec.status == "confirmed"

@pytest.mark.asyncio
async def test_provider_fallback_chain():
    class FailingProvider(LLMProvider):
        name = "fail_provider"
        async def complete(self, messages, schema=None):
            raise ConnectionError("Server unavailable")

    class WorkingProvider(LLMProvider):
        name = "fallback_working"
        async def complete(self, messages, schema=None):
            return {"skill": "set_alarm", "params": {"time": "7 am"}, "target": "phone", "confidence": 0.9}

    providers = [FailingProvider(), WorkingProvider()]
    res = await llm_orchestrator.complete_with_fallback(
        messages=[{"role": "user", "content": "alarm"}],
        schema={"type": "object"},
        custom_providers=providers
    )
    assert isinstance(res, dict)
    assert res["skill"] == "set_alarm"

@pytest.mark.asyncio
async def test_two_step_plan_stops_on_failure():
    user_id = "test-plan-user"
    skill_vol = skill_registry.get("set_volume")
    skill_lock = skill_registry.get("lock_device")

    intent1 = pytest.importorskip("hub.intent.resolver").ResolvedIntent(
        skill=skill_vol,
        params={"level": 70},
        target_platform="windows",
        target_device="windows",
        confidence=0.9
    )
    intent2 = pytest.importorskip("hub.intent.resolver").ResolvedIntent(
        skill=skill_lock,
        params={},
        target_platform="windows",
        target_device="windows",
        confidence=0.9
    )

    # Windows is offline, so step 1 will fail immediately
    plan = [intent1, intent2]
    res = await command_router.execute_plan(
        user_id=user_id,
        sender_device_id="phone-1",
        plan=plan
    )

    assert res["status"] == "failed"
    assert res["failed_step"] == 1
    assert len(res["completed_steps"]) == 1

def test_api_text_command_flow(client):
    phone = register_user_and_phone(client)
    pc = pair_pc(client, phone["token"])

    headers = {"Authorization": f"Bearer {phone['token']}"}

    # 1. Test "lock my pc" -> requires confirmation
    res_lock = client.post("/command/text", headers=headers, json={"text": "lock my pc"})
    assert res_lock.status_code == 200
    data_lock = res_lock.json()
    assert data_lock["status"] == "confirm_required"
    assert "confirmation_id" in data_lock
    conf_id = data_lock["confirmation_id"]

    # Cancel confirmation
    res_cancel = client.post("/command/cancel", headers=headers, json={"confirmation_id": conf_id})
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "cancelled"

    # 2. Test incomplete "send a message" -> clarify
    res_msg = client.post("/command/text", headers=headers, json={"text": "send a message"})
    assert res_msg.status_code == 200
    data_msg = res_msg.json()
    assert data_msg["status"] == "clarify"
    assert "recipient" in data_msg["missing_slots"]
