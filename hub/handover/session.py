import time
import uuid
from typing import Dict, Any, Optional
from hub.config import settings

class HandoverRecord:
    def __init__(
        self,
        handover_id: str,
        user_id: str,
        from_device_id: str,
        to_device_id: str,
        context_type: str,  # conversation, link, plan, app
        summary: str,
        state: Dict[str, Any],
        timeout_sec: float = settings.HANDOVER_EXPIRE_SECONDS
    ):
        self.handover_id = handover_id
        self.user_id = user_id
        self.from_device_id = from_device_id
        self.to_device_id = to_device_id
        self.context_type = context_type
        self.summary = summary
        self.state = state
        self.status = "pending"  # pending, accepted, declined, expired
        self.created_at = time.time()
        self.expires_at = self.created_at + timeout_sec

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_request_message(self) -> Dict[str, Any]:
        return {
            "type": "handover_request",
            "handover_id": self.handover_id,
            "from_device": self.from_device_id,
            "summary": self.summary,
            "context_type": self.context_type
        }

    def to_state_message(self) -> Dict[str, Any]:
        return {
            "type": "handover_state",
            "handover_id": self.handover_id,
            "context_type": self.context_type,
            "state": self.state
        }
