import time
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from hub.main import app
from hub.db import Base, engine
from hub.skills import init_skills
from hub.reliability.breaker import CircuitBreaker, CircuitState, circuit_registry
from hub.reliability.idempotency import idempotency_store
from hub.llm import llm_orchestrator, MockLLMProvider
from hub.intent.rules import match_rules

@pytest.fixture(autouse=True)
def setup_db():
    init_skills()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    circuit_registry.reset_all()
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_command_idempotency_deduplication():
    """
    Verify command ID deduplication prevents executing a command twice within the TTL window.
    """
    idempotency_store.cleanup()
    cmd_id = "test-cmd-idempotent-1"

    # First attempt: not a duplicate
    is_dup1, res1 = idempotency_store.check_or_set(cmd_id)
    assert is_dup1 is False
    assert res1 is None

    # Complete with result
    idempotency_store.complete(cmd_id, {"status": "success", "val": 42})

    # Second attempt: is a duplicate, returns cached result
    is_dup2, res2 = idempotency_store.check_or_set(cmd_id)
    assert is_dup2 is True
    assert res2 == {"status": "success", "val": 42}

def test_circuit_breaker_transitions():
    """
    Verify CircuitBreaker state transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED.
    """
    breaker = CircuitBreaker("test_provider", failure_threshold=3, recovery_timeout=0.1)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.can_execute() is True

    # 3 failures -> trips to OPEN
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # In OPEN before recovery timeout: cannot execute
    assert breaker.can_execute() is False

    # Wait for recovery timeout (0.1s)
    time.sleep(0.12)
    # Transition to HALF_OPEN trial
    assert breaker.can_execute() is True
    assert breaker.state == CircuitState.HALF_OPEN

    # Success restores to CLOSED
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0

def test_llm_provider_failover_when_circuit_open():
    """
    Verify LLM orchestrator skips providers whose circuit breaker is OPEN
    and fails over to the next healthy provider.
    """
    prov1 = MockLLMProvider()
    prov1.name = "flaky_cloud_1"
    prov2 = MockLLMProvider()
    prov2.name = "healthy_cloud_2"
    prov2.set_response({"skill": "set_volume", "params": {"level": 50}, "target": "phone"})

    # Trip breaker for prov1
    breaker1 = circuit_registry.get_breaker(prov1.name, failure_threshold=2, recovery_timeout=10.0)
    breaker1.record_failure()
    breaker1.record_failure()
    assert breaker1.state == CircuitState.OPEN

    import asyncio
    result = asyncio.run(llm_orchestrator.complete_with_fallback(
        messages=[{"role": "user", "content": "set volume to 50"}],
        custom_providers=[prov1, prov2]
    ))
    assert result["skill"] == "set_volume"
    assert len(prov1.call_history) == 0  # Skipped because breaker is OPEN
    assert len(prov2.call_history) == 1

def test_offline_mode_rule_matching():
    """
    Verify offline mode handles standard commands via local rule matching
    when all external cloud providers are down or disabled.
    """
    match = match_rules("lock my pc")
    assert match is not None
    assert match.skill_name == "lock_device"
    assert match.explicit_target == "pc"

    match_vol = match_rules("set volume to 40")
    assert match_vol is not None
    assert match_vol.skill_name == "set_volume"
    assert match_vol.params["level"] == 40

def test_health_and_metrics_endpoints(client):
    """
    Verify GET /health returns DB & breaker status, and GET /metrics returns Prometheus text.
    """
    # 1. /health
    health_res = client.get("/health")
    assert health_res.status_code == 200
    data = health_res.json()
    assert data["status"] == "healthy"
    assert data["database"] is True
    assert "circuit_breakers" in data
    assert "uptime_seconds" in data

    # 2. /metrics
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    body = metrics_res.text
    assert "beru_connected_devices" in body
    assert "beru_commands_total" in body
    assert "beru_hub_uptime_seconds" in body

def test_protocol_version_enforcement(client):
    """
    Verify clients sending older, unsupported protocol versions are rejected with WS 1002
    and an informative message instructing them to update.
    """
    reg_res = client.post("/register-first-device", json={
        "device_name": "Protocol Test",
        "platform": "android",
        "capabilities": ["set_volume"]
    })
    token = reg_res.json()["token"]

    # 1. Connect with current protocol 2.0 -> succeeds
    with client.websocket_connect(f"/ws?token={token}&protocol_version=2.0") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "devices"

    # 2. Connect with old unsupported protocol 0.5 -> rejected with 1002
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws?token={token}&protocol_version=0.5"):
            pass
    assert exc.value.code == 1002
