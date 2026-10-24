import pytest
from hub.skills.base import skill_registry
from hub.skills import init_skills

@pytest.fixture(autouse=True)
def ensure_skills_initialized():
    init_skills()

def test_starter_skills_registered():
    expected_skills = [
        "lock_device",
        "set_volume",
        "open_app",
        "toggle_flashlight",
        "set_alarm",
        "set_reminder",
        "send_message"
    ]
    for name in expected_skills:
        skill = skill_registry.get(name)
        assert skill is not None, f"Skill {name} was not found in registry"
        assert skill.name == name
        assert len(skill.supported_platforms) > 0
        assert skill.default_target in ("self", "phone", "pc")
        assert skill.confirmation in ("none", "soft", "hard")

def test_lock_device_skill():
    skill = skill_registry.get("lock_device")
    assert skill.confirmation == "hard"
    assert "windows" in skill.supported_platforms
    assert skill.default_target == "pc"

    # Valid empty or with params
    valid, instance, err = skill.validate_params({})
    assert valid is True
    assert instance.force is False

    valid, instance, err = skill.validate_params({"force": True, "message": "Locking"})
    assert valid is True
    assert instance.force is True
    assert instance.message == "Locking"

def test_set_volume_skill_validation():
    skill = skill_registry.get("set_volume")
    assert skill.confirmation == "none"

    # Missing required 'level'
    assert skill.get_missing_fields({}) == ["level"]
    valid, _, _ = skill.validate_params({})
    assert valid is False

    # Valid level
    valid, instance, _ = skill.validate_params({"level": 75})
    assert valid is True
    assert instance.level == 75

    # Out of bounds level
    valid, _, _ = skill.validate_params({"level": 150})
    assert valid is False

def test_open_app_skill_validation():
    skill = skill_registry.get("open_app")
    assert skill.get_missing_fields({}) == ["app_name"]

    valid, instance, _ = skill.validate_params({"app_name": "Chrome"})
    assert valid is True
    assert instance.app_name == "Chrome"

def test_toggle_flashlight_skill():
    skill = skill_registry.get("toggle_flashlight")
    assert skill.supported_platforms == ["android"]
    assert skill.default_target == "phone"

    valid, instance, _ = skill.validate_params({"state": "on"})
    assert valid is True
    assert instance.state == "on"

def test_set_alarm_skill_validation():
    skill = skill_registry.get("set_alarm")
    assert skill.get_missing_fields({}) == ["time"]

    valid, instance, _ = skill.validate_params({"time": "6:00 AM"})
    assert valid is True
    assert instance.time == "6:00 AM"

def test_set_reminder_skill_validation():
    skill = skill_registry.get("set_reminder")
    assert skill.get_missing_fields({}) == ["title"]

    valid, instance, _ = skill.validate_params({"title": "Buy groceries", "time": "5 pm"})
    assert valid is True
    assert instance.title == "Buy groceries"
    assert instance.time == "5 pm"

def test_send_message_skill_validation():
    skill = skill_registry.get("send_message")
    assert skill.confirmation == "hard"
    assert set(skill.get_missing_fields({})) == {"recipient", "message"}

    valid, instance, _ = skill.validate_params({"recipient": "Alice", "message": "Hello!"})
    assert valid is True
    assert instance.recipient == "Alice"
    assert instance.message == "Hello!"
    assert instance.app == "whatsapp"

def test_to_llm_specs():
    specs = skill_registry.to_llm_specs()
    assert len(specs) >= 7
    skill_names = [s["name"] for s in specs]
    assert "lock_device" in skill_names
    assert "send_message" in skill_names
