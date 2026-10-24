import pytest
from starlette.testclient import TestClient
from hub.main import app
from hub.db import Base, engine
from hub.config import settings
from hub.personalization.store import preference_store
from hub.personalization.learner import learner
from hub.personalization.context import context_builder
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

def register_user(client, name="User1") -> dict:
    res = client.post("/register-first-device", json={
        "device_name": f"{name} Phone",
        "platform": "android"
    })
    return res.json()

@pytest.mark.asyncio
async def test_preference_changes_target_resolution():
    user_id = "user-123"

    # Default volume without preference on android targets android (self)
    intents_default = await intent_resolver.resolve("set volume to 40", sender_platform="android", user_id=user_id)
    assert intents_default[0].target_platform == "android"

    # Set user preference: default target for set_volume is windows
    preference_store.set_preference(user_id, "default_targets", {"set_volume": "windows"})

    # Now resolving "set volume to 40" defaults to windows!
    intents_pref = await intent_resolver.resolve("set volume to 40", sender_platform="android", user_id=user_id)
    assert intents_pref[0].target_platform == "windows"

@pytest.mark.asyncio
async def test_preferred_app_and_contact_nickname():
    user_id = "user-456"

    preference_store.set_preference(user_id, "preferred_apps", {"music": "Spotify"})
    preference_store.set_preference(user_id, "contacts", {"mom": "Alice Smith"})

    # open_app with music category resolves to Spotify
    intents_app = await intent_resolver.resolve("open music", sender_platform="android", user_id=user_id)
    assert intents_app[0].params["app_name"] == "Spotify"

    # send_message to mom resolves to Alice Smith
    intents_msg = await intent_resolver.resolve("send a message to mom saying hello", sender_platform="android", user_id=user_id)
    assert intents_msg[0].params["recipient"] == "Alice Smith"

@pytest.mark.asyncio
async def test_device_alias_resolution():
    user_id = "user-789"
    preference_store.set_preference(user_id, "device_aliases", {"workstation": "windows"})

    intents = await intent_resolver.resolve("lock workstation", sender_platform="android", user_id=user_id)
    assert intents[0].target_platform == "windows"

def test_repeated_correction_triggers_suggestion_and_decline():
    user_id = "user-learner"
    skill = "set_volume"

    # Corrections 1 and 2: no suggestion yet
    sug1 = learner.record_correction(user_id, skill, intended_target="windows", corrected_target="android")
    assert sug1 is None

    sug2 = learner.record_correction(user_id, skill, intended_target="windows", corrected_target="android")
    assert sug2 is None

    # 3rd correction: triggers suggestion once!
    sug3 = learner.record_correction(user_id, skill, intended_target="windows", corrected_target="android")
    assert sug3 is not None
    assert "Should I always do that on your phone?" in sug3

    # If user declines ("no"), suggestion is suppressed
    learner.decline_correction_suggestion(user_id, skill, corrected_target="android")

    # 4th correction: suppressed, no suggestion
    sug4 = learner.record_correction(user_id, skill, intended_target="windows", corrected_target="android")
    assert sug4 is None

def test_accepted_correction_saves_learned_preference():
    user_id = "user-learner-accept"
    skill = "lock_device"

    learner.record_correction(user_id, skill, "android", "windows")
    learner.record_correction(user_id, skill, "android", "windows")
    sug = learner.record_correction(user_id, skill, "android", "windows")
    assert sug is not None

    # Accept suggestion
    learner.accept_correction_suggestion(user_id, skill, "windows")

    defaults = preference_store.get_preference(user_id, "default_targets")
    assert defaults["lock_device"] == "windows"

    records = preference_store.get_all_preference_records(user_id)
    target_rec = next(r for r in records if r["key"] == "default_targets")
    assert target_rec["source"] == "learned"

def test_remembered_facts_crud():
    user_id = "user-facts"

    # Add facts
    id1 = preference_store.add_fact(user_id, "My gym card is in the blue bag")
    id2 = preference_store.add_fact(user_id, "WiFi password is SuperSecret123")

    # Search facts
    results = preference_store.search_facts(user_id, "gym card")
    assert len(results) == 1
    assert "blue bag" in results[0]["text"]

    # Delete fact
    deleted = preference_store.delete_fact(user_id, id1)
    assert deleted is True

    remaining = preference_store.get_all_facts(user_id)
    assert len(remaining) == 1
    assert "WiFi password" in remaining[0]["text"]

def test_context_builder_injection_and_cap():
    user_id = "user-ctx"
    preference_store.set_preference(user_id, "device_aliases", {"laptop": "windows"})
    preference_store.set_preference(user_id, "preferred_apps", {"music": "Spotify"})
    preference_store.add_fact(user_id, "Gym card is in the blue bag")

    # Query matching music and gym card
    ctx = context_builder.build_context(user_id, "play music and where is my gym card")
    assert "Preferred Apps: {'music': 'Spotify'}" in ctx
    assert "Gym card is in the blue bag" in ctx
    # Irrelevant laptop alias not injected
    assert "laptop" not in ctx

    # Verify size cap
    assert len(ctx) <= settings.CONTEXT_INJECTION_MAX_CHARS

def test_personalization_api_and_isolation(client):
    user_a = register_user(client, "Alice")
    user_b = register_user(client, "Bob")

    token_a = user_a["token"]
    token_b = user_b["token"]

    # Alice saves a preference
    put_res = client.put(
        "/personalization/preferences/test_pref",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"value": "alice_secret"}
    )
    assert put_res.status_code == 200

    # Bob cannot see Alice's preference
    bob_overview = client.get("/personalization", headers={"Authorization": f"Bearer {token_b}"})
    assert bob_overview.status_code == 200
    bob_prefs = [p["key"] for p in bob_overview.json()["preferences"]]
    assert "test_pref" not in bob_prefs

    # Alice exports data
    export_res = client.post("/personalization/export", headers={"Authorization": f"Bearer {token_a}"})
    assert export_res.status_code == 200
    assert any(p["key"] == "test_pref" for p in export_res.json()["preferences"])

    # Alice resets all
    del_res = client.delete("/personalization", headers={"Authorization": f"Bearer {token_a}"})
    assert del_res.status_code == 200

    after_reset = client.get("/personalization", headers={"Authorization": f"Bearer {token_a}"})
    assert len(after_reset.json()["preferences"]) == 0
