import pytest
from hub.skills import init_skills
from hub.intent.rules import match_rules
from hub.intent.resolver import intent_resolver, resolve_target_platform
from hub.llm import llm_orchestrator, MockLLMProvider

@pytest.fixture(autouse=True)
def setup_env():
    init_skills()
    llm_orchestrator.mock_provider = None
    yield
    llm_orchestrator.mock_provider = None

def test_rule_matching_common_phrasings():
    # Lock PC
    m1 = match_rules("lock my pc")
    assert m1 is not None
    assert m1.skill_name == "lock_device"
    assert m1.explicit_target == "pc"
    assert m1.confidence >= 0.9

    # Set volume
    m2 = match_rules("set volume to 65")
    assert m2 is not None
    assert m2.skill_name == "set_volume"
    assert m2.params["level"] == 65

    # Flashlight
    m3 = match_rules("turn on flashlight")
    assert m3 is not None
    assert m3.skill_name == "toggle_flashlight"
    assert m3.params["state"] == "on"

    # Set alarm
    m4 = match_rules("set an alarm for 6 am")
    assert m4 is not None
    assert m4.skill_name == "set_alarm"
    assert m4.params["time"] == "6 am"

    # Send message
    m5 = match_rules("send a message to Bob saying Running late")
    assert m5 is not None
    assert m5.skill_name == "send_message"
    assert m5.params["recipient"] == "Bob"
    assert m5.params["message"] == "Running late"

@pytest.mark.asyncio
async def test_low_confidence_falls_through_to_llm():
    mock = MockLLMProvider()
    mock.set_response({
        "skill": "open_app",
        "params": {"app_name": "Spotify"},
        "target": "pc",
        "confidence": 0.9
    })
    llm_orchestrator.mock_provider = mock

    # An unusual phrasing that rules won't high-confidence match
    intents = await intent_resolver.resolve(
        text="Could you please fire up that music player Spotify on my workstation",
        sender_platform="android"
    )

    assert len(intents) == 1
    assert intents[0].skill.name == "open_app"
    assert intents[0].params["app_name"] == "Spotify"
    assert intents[0].target_platform == "windows"

def test_target_resolution_explicit():
    # Explicit laptop -> windows
    t1 = resolve_target_platform(explicit_target="laptop", default_target="phone", sender_platform="android")
    assert t1 == "windows"

    # Explicit phone -> android
    t2 = resolve_target_platform(explicit_target="phone", default_target="pc", sender_platform="windows")
    assert t2 == "android"

def test_target_resolution_default():
    # No explicit target -> uses skill's default_target (e.g. pc -> windows)
    t = resolve_target_platform(explicit_target=None, default_target="pc", sender_platform="android")
    assert t == "windows"

def test_target_resolution_sender_fallback():
    # Default target 'self' -> sender's platform
    t = resolve_target_platform(explicit_target=None, default_target="self", sender_platform="windows")
    assert t == "windows"

@pytest.mark.asyncio
async def test_unsupported_platform_fails_with_clear_message():
    # toggle_flashlight is only supported on android
    # Try running on windows
    intents = await intent_resolver.resolve(
        text="turn on flashlight on my pc",
        sender_platform="windows"
    )
    assert len(intents) == 1
    assert intents[0].error is not None
    assert "Platform 'windows' does not support skill 'toggle_flashlight'" in intents[0].error

@pytest.mark.asyncio
async def test_contextual_follow_up():
    # 1. First command
    first = await intent_resolver.resolve("set volume to 80", sender_platform="android")
    assert len(first) == 1

    # 2. Follow-up "do the same on my laptop"
    second = await intent_resolver.resolve(
        text="do the same on my laptop",
        sender_platform="android",
        context_intent=first[0]
    )
    assert len(second) == 1
    assert second[0].skill.name == "set_volume"
    assert second[0].params["level"] == 80
    assert second[0].target_platform == "windows"
