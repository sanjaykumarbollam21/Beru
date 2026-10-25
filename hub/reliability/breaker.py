import time
import logging
from enum import Enum
from typing import Dict, Optional, Callable, Any
from hub.config import settings

logger = logging.getLogger(__name__)

class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: requests pass through
    OPEN = "OPEN"            # Tripped: requests fail fast or fail over
    HALF_OPEN = "HALF_OPEN"  # Trial period: tests if service has recovered

class CircuitBreaker:
    """
    Circuit breaker for external providers (LLM, STT, TTS).
    Prevents cascading hangs when a provider is degraded or down.
    """
    def __init__(
        self,
        name: str,
        failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = settings.CIRCUIT_BREAKER_RECOVERY_SECONDS
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()
        self.last_failure_time = 0.0

    def can_execute(self) -> bool:
        """
        Determines if a request should be attempted.
        """
        now = time.time()
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if now - self.last_state_change >= self.recovery_timeout:
                logger.info(f"Circuit breaker '{self.name}' transitioning from OPEN to HALF_OPEN (trial)")
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow trial request
            return True

        return False

    def record_success(self):
        """
        Records a successful operation. Recovers from HALF_OPEN to CLOSED.
        """
        if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            logger.info(f"Circuit breaker '{self.name}' recovered: transitioning to CLOSED.")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()

    def record_failure(self):
        """
        Records an operation failure. Trips from CLOSED/HALF_OPEN to OPEN.
        """
        now = time.time()
        self.failure_count += 1
        self.last_failure_time = now

        if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            logger.warning(
                f"Circuit breaker '{self.name}' TRIPPED: state=OPEN (failures={self.failure_count}, threshold={self.failure_threshold})"
            )
            self.state = CircuitState.OPEN
            self.last_state_change = now

    def reset(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()


class CircuitBreakerRegistry:
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get_breaker(
        self,
        name: str,
        failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = settings.CIRCUIT_BREAKER_RECOVERY_SECONDS
    ) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout
            )
        return self._breakers[name]

    def all_states(self) -> Dict[str, str]:
        return {name: b.state.value for name, b in self._breakers.items()}

    def reset_all(self):
        for b in self._breakers.values():
            b.reset()

circuit_registry = CircuitBreakerRegistry()
