import time
import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from hub.intent.resolver import ResolvedIntent, intent_resolver
from hub.config import settings

logger = logging.getLogger(__name__)

SLOT_QUESTIONS = {
    "recipient": "Who would you like to send the message to?",
    "message": "What would you like the message to say?",
    "level": "What volume level (0 to 100) would you like to set?",
    "time": "What time would you like to set it for?",
    "title": "What should the reminder be for?",
    "app_name": "Which app would you like to open?"
}

@dataclass
class DialogTurnResult:
    type: str  # "ready", "clarify", "confirm_request", "error", "unknown"
    intent: Optional[ResolvedIntent] = None
    plan: List[ResolvedIntent] = field(default_factory=list)
    question: Optional[str] = None
    missing_slots: List[str] = field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None

@dataclass
class UserDialogState:
    user_id: str
    turns: List[Dict[str, Any]] = field(default_factory=list)
    pending_intent: Optional[ResolvedIntent] = None
    pending_plan: List[ResolvedIntent] = field(default_factory=list)
    pending_since: float = 0.0
    last_resolved_intent: Optional[ResolvedIntent] = None

    def add_turn(self, role: str, text: str):
        self.turns.append({
            "role": role,
            "text": text,
            "timestamp": time.time()
        })
        # Keep last 20 turns
        if len(self.turns) > 20:
            self.turns = self.turns[-20:]

    def is_pending_expired(self, timeout: float = settings.SLOT_FILLING_TIMEOUT_SECONDS) -> bool:
        if not self.pending_intent:
            return True
        return (time.time() - self.pending_since) > timeout

    def clear_pending(self):
        self.pending_intent = None
        self.pending_plan = []
        self.pending_since = 0.0

class DialogManager:
    def __init__(self):
        self._states: Dict[str, UserDialogState] = {}

    def get_state(self, user_id: str) -> UserDialogState:
        if user_id not in self._states:
            self._states[user_id] = UserDialogState(user_id=user_id)
        return self._states[user_id]

    def _fill_slot_from_reply(self, slot: str, reply: str) -> Any:
        cleaned = reply.strip()
        if slot == "level":
            match = re.search(r"\b(\d+)\b", cleaned)
            if match:
                return int(match.group(1))
        elif slot == "recipient":
            # Strip "to ", "message "
            cleaned = re.sub(r"^(?:to|message|send to)\s+", "", cleaned, flags=re.IGNORECASE)
            # If user said "Alice saying hello"
            parts = re.split(r"\s+saying\s+", cleaned, flags=re.IGNORECASE)
            return parts[0].strip()
        return cleaned

    async def process_user_text(
        self,
        user_id: str,
        text: str,
        sender_platform: str = "android",
        sender_device_id: Optional[str] = None
    ) -> DialogTurnResult:
        state = self.get_state(user_id)
        state.add_turn("user", text)

        # 1. Check if there is an active, unexpired pending intent waiting for slot filling
        if state.pending_intent and not state.is_pending_expired():
            pending = state.pending_intent
            missing = pending.skill.get_missing_fields(pending.params)

            if missing:
                current_slot = missing[0]
                extracted_val = self._fill_slot_from_reply(current_slot, text)
                pending.params[current_slot] = extracted_val

                # If user said "Alice saying I'll be late", also check if message was provided
                if current_slot == "recipient" and "message" in missing:
                    match_msg = re.search(r"\s+saying\s+(.+)$", text, re.IGNORECASE)
                    if match_msg:
                        pending.params["message"] = match_msg.group(1).strip()

                # Re-check remaining missing slots
                remaining_missing = pending.skill.get_missing_fields(pending.params)
                pending.missing_slots = remaining_missing

                if remaining_missing:
                    next_slot = remaining_missing[0]
                    question = SLOT_QUESTIONS.get(next_slot, f"Please provide the {next_slot}.")
                    state.add_turn("assistant", question)
                    return DialogTurnResult(
                        type="clarify",
                        intent=pending,
                        question=question,
                        missing_slots=remaining_missing
                    )
                else:
                    # All slots filled!
                    completed_intent = pending
                    plan = [completed_intent] + state.pending_plan
                    state.clear_pending()
                    state.last_resolved_intent = completed_intent

                    return DialogTurnResult(
                        type="ready",
                        intent=completed_intent,
                        plan=plan
                    )
        else:
            state.clear_pending()

        # 2. Fresh intent resolution
        resolved_plan = await intent_resolver.resolve(
            text=text,
            sender_platform=sender_platform,
            sender_device_id=sender_device_id,
            context_intent=state.last_resolved_intent
        )

        if not resolved_plan:
            msg = "I didn't understand that command."
            state.add_turn("assistant", msg)
            return DialogTurnResult(type="unknown", message=msg)

        first_intent = resolved_plan[0]

        # Check for platform support errors
        if first_intent.error:
            state.add_turn("assistant", first_intent.error)
            return DialogTurnResult(
                type="error",
                error=first_intent.error,
                intent=first_intent
            )

        # Check for missing required slots
        if first_intent.missing_slots:
            state.pending_intent = first_intent
            state.pending_plan = resolved_plan[1:]
            state.pending_since = time.time()

            first_missing = first_intent.missing_slots[0]
            question = SLOT_QUESTIONS.get(first_missing, f"Please specify the {first_missing}.")
            state.add_turn("assistant", question)

            return DialogTurnResult(
                type="clarify",
                intent=first_intent,
                question=question,
                missing_slots=first_intent.missing_slots
            )

        state.last_resolved_intent = first_intent
        return DialogTurnResult(
            type="ready",
            intent=first_intent,
            plan=resolved_plan
        )

dialog_manager = DialogManager()
