import logging
import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger("beru.audit")

class SecurityAuditLogger:
    """
    Append-only structured security audit logger.
    Logs IDs, timestamps, and outcomes only - never sensitive user data or message bodies.
    """
    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path
        self._memory_log: List[Dict[str, Any]] = []

    def log_event(
        self,
        event_type: str,
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        outcome: str = "success",
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "device_id": device_id,
            "ip_address": ip_address,
            "outcome": outcome,
            "details": details or {}
        }
        self._memory_log.append(record)
        # Keep in-memory log bounded (last 1000 records)
        if len(self._memory_log) > 1000:
            self._memory_log.pop(0)

        log_msg = f"AUDIT_EVENT: {event_type} outcome={outcome} user={user_id} dev={device_id} ip={ip_address}"
        if outcome == "success":
            logger.info(log_msg)
        else:
            logger.warning(log_msg)

        if self.log_path:
            try:
                os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
            except Exception as e:
                logger.error(f"Failed to append to audit log file: {e}")

        return record

    def get_events(
        self,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        results = self._memory_log
        if event_type:
            results = [e for e in results if e["event_type"] == event_type]
        if user_id:
            results = [e for e in results if e["user_id"] == user_id]
        return results[-limit:]

    def clear(self):
        self._memory_log.clear()

audit_logger = SecurityAuditLogger()
