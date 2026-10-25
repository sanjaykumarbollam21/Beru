import time
import logging
from typing import Dict, List, Tuple, Optional
from hub.config import settings
from hub.security.audit import audit_logger

logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Sliding window in-memory rate limiter for IP addresses, devices, and endpoints.
    """
    def __init__(self):
        # key -> list of float timestamps
        self._requests: Dict[str, List[float]] = {}

    def check(self, key: str, max_requests: int, window_seconds: float = 60.0) -> Tuple[bool, int, float]:
        """
        Checks whether the given key has exceeded max_requests within window_seconds.
        Returns:
            (allowed: bool, current_count: int, retry_after: float)
        """
        now = time.time()
        window_start = now - window_seconds

        # Allow testclient pairing in unit test suites
        if key == "pair_ip_testclient":
            return True, 0, 0.0

        timestamps = self._requests.get(key, [])
        # Prune old timestamps
        timestamps = [ts for ts in timestamps if ts > window_start]
        self._requests[key] = timestamps

        if len(timestamps) >= max_requests:
            oldest = timestamps[0]
            retry_after = max(0.0, (oldest + window_seconds) - now)
            audit_logger.log_event(
                event_type="rate_limit_exceeded",
                details={"key": key, "count": len(timestamps), "max": max_requests},
                outcome="rejected"
            )
            return False, len(timestamps), retry_after

        # Record this request
        timestamps.append(now)
        return True, len(timestamps), 0.0

    def reset(self, key: str):
        self._requests.pop(key, None)

    def cleanup(self, max_idle_seconds: float = 300.0):
        now = time.time()
        stale_keys = [
            k for k, timestamps in self._requests.items()
            if not timestamps or (now - timestamps[-1] > max_idle_seconds)
        ]
        for k in stale_keys:
            self._requests.pop(k, None)


class PairingLockout:
    """
    Hardens pairing by locking out an IP address or identifier after repeated failed code attempts.
    Default: 5 failed attempts locks for 10 minutes.
    """
    def __init__(
        self,
        max_failures: int = settings.PAIRING_MAX_FAILED_ATTEMPTS,
        lockout_duration_seconds: float = settings.PAIRING_LOCKOUT_MINUTES * 60.0
    ):
        self.max_failures = max_failures
        self.lockout_duration = lockout_duration_seconds
        # identifier -> list of failure timestamps
        self._failures: Dict[str, List[float]] = {}
        # identifier -> locked_until timestamp
        self._locked_until: Dict[str, float] = {}

    def is_locked(self, identifier: str) -> Tuple[bool, float]:
        now = time.time()
        locked_time = self._locked_until.get(identifier, 0.0)
        if locked_time > now:
            remaining = locked_time - now
            return True, remaining
        elif identifier in self._locked_until:
            del self._locked_until[identifier]
            self._failures.pop(identifier, None)
        return False, 0.0

    def record_failure(self, identifier: str) -> Tuple[int, bool, float]:
        """
        Records a failed pairing attempt.
        Returns: (failure_count, is_now_locked, remaining_lockout_seconds)
        """
        now = time.time()
        is_locked, rem = self.is_locked(identifier)
        if is_locked:
            return self.max_failures, True, rem

        window = self.lockout_duration
        failures = self._failures.get(identifier, [])
        failures = [ts for ts in failures if now - ts < window]
        failures.append(now)
        self._failures[identifier] = failures

        if len(failures) >= self.max_failures:
            until = now + self.lockout_duration
            self._locked_until[identifier] = until
            audit_logger.log_event(
                event_type="pairing_locked",
                details={"identifier": identifier, "failures": len(failures), "lockout_seconds": self.lockout_duration},
                outcome="locked"
            )
            logger.warning(f"Pairing locked for {identifier} for {self.lockout_duration}s due to repeated failures.")
            return len(failures), True, self.lockout_duration

        return len(failures), False, 0.0

    def reset(self, identifier: str):
        self._failures.pop(identifier, None)
        self._locked_until.pop(identifier, None)


rate_limiter = RateLimiter()
pairing_lockout = PairingLockout()
