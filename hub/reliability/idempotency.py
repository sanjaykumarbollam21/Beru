import time
import logging
from typing import Dict, Any, Optional
from hub.config import settings

logger = logging.getLogger(__name__)

class IdempotencyRecord:
    def __init__(self, command_id: str, timestamp: float, result: Optional[Any] = None, in_flight: bool = True):
        self.command_id = command_id
        self.timestamp = timestamp
        self.result = result
        self.in_flight = in_flight

class IdempotencyStore:
    """
    Deduplicates repeated command IDs for 5 minutes (configurable).
    Ensures network retries do not re-execute side-effecting skills twice.
    """
    def __init__(self, ttl_seconds: float = settings.IDEMPOTENCY_TTL_SECONDS):
        self.ttl = ttl_seconds
        # command_id -> IdempotencyRecord
        self._store: Dict[str, IdempotencyRecord] = {}

    def check_or_set(self, command_id: str) -> Tuple_Check:
        """
        Atomically checks if command_id was already received.
        If not seen, registers it as in_flight and returns (is_duplicate=False, cached_result=None).
        If already seen, returns (is_duplicate=True, cached_result).
        """
        self.cleanup()
        now = time.time()
        record = self._store.get(command_id)
        if record:
            logger.info(f"Command ID {command_id} is a duplicate (in_flight={record.in_flight}).")
            return True, record.result

        self._store[command_id] = IdempotencyRecord(
            command_id=command_id,
            timestamp=now,
            result=None,
            in_flight=True
        )
        return False, None

    def complete(self, command_id: str, result: Any):
        """
        Stores the completed result for the command ID so future duplicates return the same result.
        """
        if command_id in self._store:
            record = self._store[command_id]
            record.result = result
            record.in_flight = False

    def is_duplicate(self, command_id: str) -> bool:
        self.cleanup()
        return command_id in self._store

    def cleanup(self):
        now = time.time()
        expired = [cid for cid, rec in self._store.items() if now - rec.timestamp > self.ttl]
        for cid in expired:
            del self._store[cid]

# Type helper for clarity
Tuple_Check = tuple[bool, Optional[Any]]

idempotency_store = IdempotencyStore()
