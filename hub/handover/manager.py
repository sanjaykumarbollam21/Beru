import time
import uuid
import logging
from typing import Dict, Optional, Tuple, Any
from hub.handover.session import HandoverRecord
from hub.registry import registry
from hub.dialog import dialog_manager

logger = logging.getLogger(__name__)

class HandoverManager:
    def __init__(self):
        # handover_id -> HandoverRecord
        self._records: Dict[str, HandoverRecord] = {}
        # user_id -> active_device_id
        self._active_devices: Dict[str, str] = {}

    def get_active_device(self, user_id: str) -> Optional[str]:
        return self._active_devices.get(user_id)

    def set_active_device(self, user_id: str, device_id: str):
        self._active_devices[user_id] = device_id
        logger.info(f"User {user_id} active device set to {device_id}")

    def create_handover(
        self,
        user_id: str,
        from_device_id: str,
        to_device_id: str,
        context_type: str = "conversation",
        custom_state: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None
    ) -> HandoverRecord:
        handover_id = f"ho-{uuid.uuid4().hex[:8]}"

        # Snapshot current session state
        dialog_state = dialog_manager.get_state(user_id)
        snapshot_state: Dict[str, Any] = {
            "turns": list(dialog_state.turns),
            "pending_missing_slots": list(dialog_state.pending_intent.missing_slots) if dialog_state.pending_intent else []
        }
        if dialog_state.last_resolved_intent:
            snapshot_state["last_skill"] = dialog_state.last_resolved_intent.skill.name
            snapshot_state["last_params"] = dialog_state.last_resolved_intent.params

        if custom_state:
            snapshot_state.update(custom_state)

        if not summary:
            if context_type == "link":
                url = snapshot_state.get("url", "web page")
                summary = f"Continue viewing {url}"
            elif context_type == "plan":
                summary = "Resume pending action plan"
            else:
                summary = "Continue conversation"

        record = HandoverRecord(
            handover_id=handover_id,
            user_id=user_id,
            from_device_id=from_device_id,
            to_device_id=to_device_id,
            context_type=context_type,
            summary=summary,
            state=snapshot_state
        )
        self._records[handover_id] = record
        return record

    async def dispatch_handover_request(self, record: HandoverRecord) -> bool:
        target = await registry.resolve_target(
            user_id=record.user_id,
            sender_device_id=record.from_device_id,
            target=record.to_device_id
        )
        if not target:
            return False

        try:
            await target.websocket.send_json(record.to_request_message())
            return True
        except Exception as e:
            logger.warning(f"Failed to send handover_request to {target.device_id}: {e}")
            return False

    async def accept_handover(
        self,
        handover_id: str,
        user_id: str,
        accepting_device_id: str
    ) -> Tuple[bool, str, Optional[HandoverRecord]]:
        record = self._records.get(handover_id)
        if not record:
            return False, "Handover record not found", None
        if record.user_id != user_id:
            return False, "Unauthorized handover request", None
        if record.is_expired():
            record.status = "expired"
            return False, "Handover request expired", None
        if record.status != "pending":
            return False, f"Handover already {record.status}", None

        record.status = "accepted"

        # Update active device
        self.set_active_device(user_id, accepting_device_id)

        # 1. Send handover_state to accepting device
        accepting_dev = await registry.resolve_target(user_id, record.from_device_id, accepting_device_id)
        if accepting_dev:
            try:
                await accepting_dev.websocket.send_json(record.to_state_message())
            except Exception as e:
                logger.warning(f"Failed to send handover_state: {e}")

        # 2. Send handover_done to source device
        source_dev = await registry.resolve_target(user_id, accepting_device_id, record.from_device_id)
        if source_dev:
            try:
                await source_dev.websocket.send_json({
                    "type": "handover_done",
                    "handover_id": handover_id
                })
            except Exception as e:
                logger.warning(f"Failed to send handover_done: {e}")

        return True, "Handover accepted", record

    def decline_handover(self, handover_id: str, user_id: str) -> Tuple[bool, str]:
        record = self._records.get(handover_id)
        if not record:
            return False, "Handover record not found"
        if record.user_id != user_id:
            return False, "Unauthorized handover request"
        if record.is_expired():
            record.status = "expired"
            return False, "Handover request expired"

        record.status = "declined"
        return True, "Handover declined"

handover_manager = HandoverManager()
