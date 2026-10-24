import pytest
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.config import settings
from hub.personalization.routines import routine_manager
from hub.personalization.learner import learner
from hub.intent.resolver import intent_resolver

@pytest.fixture(autouse=True)
def setup_env():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def register_user(client) -> dict:
    res = client.post("/register-first-device", json={
        "device_name": "Pixel 8",
        "platform": "android"
    })
    return res.json()

def test_routine_crud(client):
    user = register_user(client)
    token = user["token"]

    # 1. Create routine via API
    create_res = client.post(
        "/personalization/routines",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "morning",
            "steps": [
                {"skill": "set_volume", "target": "self", "params": {"level": 25}},
                {"skill": "open_app", "target": "self", "params": {"app_name": "Spotify"}}
            ]
        }
    )
    assert create_res.status_code == 200
    assert create_res.json()["name"] == "morning"

    # 2. List routines
    list_res = client.get("/personalization/routines", headers={"Authorization": f"Bearer {token}"})
    assert list_res.status_code == 200
    routines = list_res.json()
    assert len(routines) == 1
    assert routines[0]["name"] == "morning"
    assert len(routines[0]["steps"]) == 2

    # 3. Delete routine
    del_res = client.delete("/personalization/routines/morning", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 200

    list_after = client.get("/personalization/routines", headers={"Authorization": f"Bearer {token}"})
    assert len(list_after.json()) == 0

@pytest.mark.asyncio
async def test_routine_resolved_by_name():
    user_id = "user-routine-resolve"
    routine_manager.create_routine(
        user_id=user_id,
        name="work mode",
        steps=[
            {"skill": "set_volume", "target": "windows", "params": {"level": 15}},
            {"skill": "lock_device", "target": "windows", "params": {}}
        ]
    )

    # Resolving "work mode" returns the multi-step plan!
    plan = await intent_resolver.resolve("work mode", sender_platform="android", user_id=user_id)
    assert len(plan) == 2
    assert plan[0].skill.name == "set_volume"
    assert plan[0].params["level"] == 15
    assert plan[1].skill.name == "lock_device"
    assert plan[1].requires_confirmation is True  # lock_device is 'hard' confirmation!

def test_repeated_skill_sequence_routine_suggestion():
    user_id = "user-seq"
    sequence = ["set_volume", "open_app"]

    # Day 1: no suggestion
    sug1 = learner.record_skill_sequence(user_id, sequence, date_str="2026-10-20")
    assert sug1 is None

    # Day 2: no suggestion
    sug2 = learner.record_skill_sequence(user_id, sequence, date_str="2026-10-21")
    assert sug2 is None

    # Day 3: triggers routine suggestion!
    sug3 = learner.record_skill_sequence(user_id, sequence, date_str="2026-10-22")
    assert sug3 is not None
    assert "Would you like to save this as a routine" in sug3

    # Day 4: does not re-suggest
    sug4 = learner.record_skill_sequence(user_id, sequence, date_str="2026-10-23")
    assert sug4 is None
