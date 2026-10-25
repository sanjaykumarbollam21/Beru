import time
import logging
from typing import Dict, List, Tuple
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from hub.db import SessionLocal
from hub.registry import registry
from hub.reliability.breaker import circuit_registry
from hub.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reliability"])

class MetricsCollector:
    """
    Collects runtime counters and latencies for Prometheus-style metric export.
    """
    def __init__(self):
        # (skill, outcome) -> count
        self._command_counts: Dict[Tuple[str, str], int] = {}
        # provider -> count
        self._provider_failures: Dict[str, int] = {}
        # outcome -> count
        self._arbitration_counts: Dict[str, int] = {}
        # Latency samples (capped to last 100)
        self._stt_latencies: List[float] = []
        self._llm_latencies: List[float] = []
        self.start_time = time.time()

    def record_command(self, skill: str, outcome: str):
        key = (skill or "unknown", outcome or "unknown")
        self._command_counts[key] = self._command_counts.get(key, 0) + 1

    def record_provider_failure(self, provider: str):
        self._provider_failures[provider] = self._provider_failures.get(provider, 0) + 1

    def record_arbitration(self, outcome: str):
        self._arbitration_counts[outcome] = self._arbitration_counts.get(outcome, 0) + 1

    def record_stt_latency(self, seconds: float):
        self._stt_latencies.append(seconds)
        if len(self._stt_latencies) > 200:
            self._stt_latencies.pop(0)

    def record_llm_latency(self, seconds: float):
        self._llm_latencies.append(seconds)
        if len(self._llm_latencies) > 200:
            self._llm_latencies.pop(0)

    def generate_prometheus(self, connected_devices_count: int) -> str:
        lines = []

        # Connected devices gauge
        lines.append("# HELP beru_connected_devices Number of currently online devices.")
        lines.append("# TYPE beru_connected_devices gauge")
        lines.append(f"beru_connected_devices {connected_devices_count}")

        # Commands counter
        lines.append("# HELP beru_commands_total Total commands executed by skill and outcome.")
        lines.append("# TYPE beru_commands_total counter")
        for (skill, outcome), count in self._command_counts.items():
            lines.append(f'beru_commands_total{{skill="{skill}",outcome="{outcome}"}} {count}')
        if not self._command_counts:
            lines.append('beru_commands_total{skill="none",outcome="none"} 0')

        # Provider failures counter
        lines.append("# HELP beru_provider_failures_total Total failure count by provider.")
        lines.append("# TYPE beru_provider_failures_total counter")
        for prov, count in self._provider_failures.items():
            lines.append(f'beru_provider_failures_total{{provider="{prov}"}} {count}')
        if not self._provider_failures:
            lines.append('beru_provider_failures_total{provider="none"} 0')

        # Wake arbitration counter
        lines.append("# HELP beru_arbitration_total Total wake arbitration decisions by outcome.")
        lines.append("# TYPE beru_arbitration_total counter")
        for outc, count in self._arbitration_counts.items():
            lines.append(f'beru_arbitration_total{{outcome="{outc}"}} {count}')
        if not self._arbitration_counts:
            lines.append('beru_arbitration_total{outcome="none"} 0')

        # Latency summaries
        avg_stt = sum(self._stt_latencies) / len(self._stt_latencies) if self._stt_latencies else 0.0
        lines.append("# HELP beru_stt_latency_seconds Average STT latency in seconds.")
        lines.append("# TYPE beru_stt_latency_seconds gauge")
        lines.append(f"beru_stt_latency_seconds {avg_stt:.4f}")

        avg_llm = sum(self._llm_latencies) / len(self._llm_latencies) if self._llm_latencies else 0.0
        lines.append("# HELP beru_llm_latency_seconds Average LLM latency in seconds.")
        lines.append("# TYPE beru_llm_latency_seconds gauge")
        lines.append(f"beru_llm_latency_seconds {avg_llm:.4f}")

        # Hub uptime
        uptime = time.time() - self.start_time
        lines.append("# HELP beru_hub_uptime_seconds Hub uptime in seconds.")
        lines.append("# TYPE beru_hub_uptime_seconds gauge")
        lines.append(f"beru_hub_uptime_seconds {uptime:.1f}")

        return "\n".join(lines) + "\n"

metrics_collector = MetricsCollector()

@router.get("/health")
def health_check():
    """
    Liveness and readiness check: verifies database connection,
    circuit breaker status, and uptime.
    """
    db_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.error(f"Health check DB ping failed: {e}")

    connected_count = len(registry._devices)
    breakers = circuit_registry.all_states()

    overall_status = "healthy" if db_ok else "unhealthy"
    status_code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    import json
    data = {
        "status": overall_status,
        "database": db_ok,
        "connected_devices": connected_count,
        "circuit_breakers": breakers,
        "uptime_seconds": round(time.time() - metrics_collector.start_time, 1)
    }

    return Response(
        content=json.dumps(data),
        media_type="application/json",
        status_code=status_code
    )

@router.get("/metrics")
def metrics_endpoint():
    """
    Prometheus-compatible metrics endpoint.
    """
    connected_count = len(registry._devices)
    metrics_text = metrics_collector.generate_prometheus(connected_count)
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4; charset=utf-8")
