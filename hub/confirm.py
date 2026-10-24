import time
import uuid
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from hub.intent.resolver import ResolvedIntent
from hub.config import settings

@dataclass
class PendingConfirmation:
    id: str
    user_id: str
    sender_device_id: str
    intent: ResolvedIntent
    remaining_plan: List[ResolvedIntent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: str = "pending"  # "pending", "confirmed", "cancelled", "expired"
    prompt: str = ""

def generate_prompt_for_intent(intent: ResolvedIntent) -> str:
    skill_name = intent.skill.name
    params = intent.params
    target = intent.target_device

    if skill_name == "lock_device":
        return f"Confirm: Lock {target} screen?"
    elif skill_name == "send_message":
        recipient = params.get("recipient", "contact")
        msg = params.get("message", "")
        return f"Confirm sending {params.get('app', 'message')} to {recipient}: \"{msg}\"?"
    return f"Confirm execution of '{skill_name}' on {target}?"

class ConfirmationGate:
    def __init__(self):
        # confirmation_id -> PendingConfirmation
        self._pending: Dict[str, PendingConfirmation] = {}

    def create_confirmation(
        self,
        user_id: str,
        sender_device_id: str,
        intent: ResolvedIntent,
        remaining_plan: Optional[List[ResolvedIntent]] = None,
        timeout: float = settings.CONFIRMATION_TIMEOUT_SECONDS
    ) -> PendingConfirmation:
        conf_id = f"conf-{uuid.uuid4().hex[:8]}"
        now = time.time()
        prompt = generate_prompt_for_intent(intent)

        record = PendingConfirmation(
            id=conf_id,
            user_id=user_id,
            sender_device_id=sender_device_id,
            intent=intent,
            remaining_plan=remaining_plan or [],
            created_at=now,
            expires_at=now + timeout,
            status="pending",
            prompt=prompt
        )
        self._pending[conf_id] = record
        return record

    def get(self, confirmation_id: str) -> Optional[PendingConfirmation]:
        record = self._pending.get(confirmation_id)
        if not record:
            return None
        if record.status == "pending" and time.time() > record.expires_at:
            record.status = "expired"
        return record

    def confirm(self, confirmation_id: str, user_id: str) -> Tuple[bool, Optional[PendingConfirmation], str]:
        record = self.get(confirmation_id)
        if not record:
            return False, None, "Confirmation request not found"
        if record.user_id != user_id:
            return False, None, "Unauthorized confirmation request"
        if record.status == "expired" or time.time() > record.expires_at:
            record.status = "expired"
            return False, record, "Confirmation request has expired"
        if record.status != "pending":
            return False, record, f"Confirmation request is already {record.status}"

        record.status = "confirmed"
        return True, record, "Confirmed"

    def cancel(self, confirmation_id: str, user_id: str) -> Tuple[bool, Optional[PendingConfirmation], str]:
        record = self.get(confirmation_id)
        if not record:
            return False, None, "Confirmation request not found"
        if record.user_id != user_id:
            return False, None, "Unauthorized confirmation request"
        if record.status == "expired" or time.time() > record.expires_at:
            record.status = "expired"
            return False, record, "Confirmation request has expired"
        if record.status != "pending":
            return False, record, f"Confirmation request is already {record.status}"

        record.status = "cancelled"
        return True, record, "Cancelled"

confirmation_gate = ConfirmationGate()
