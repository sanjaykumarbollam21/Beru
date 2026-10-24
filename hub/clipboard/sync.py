import time
import hashlib
import logging
from typing import Dict, Optional, Tuple, Any
from hub.config import settings
from hub.registry import registry

logger = logging.getLogger(__name__)

class UserClipboardState:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.latest_clip: Optional[Dict[str, Any]] = None
        # hash -> timestamp
        self.recent_hashes: Dict[str, float] = {}

    def is_clip_expired(self) -> bool:
        if not self.latest_clip:
            return True
        return (time.time() - self.latest_clip["timestamp"]) > settings.CLIPBOARD_EXPIRE_SECONDS

    def clean_old_hashes(self, window_sec: float = settings.CLIPBOARD_DEDUP_WINDOW_SECONDS):
        now = time.time()
        for h, t in list(self.recent_hashes.items()):
            if now - t > window_sec * 2:
                del self.recent_hashes[h]

class ClipboardSyncManager:
    def __init__(self):
        # user_id -> UserClipboardState
        self._states: Dict[str, UserClipboardState] = {}

    def get_state(self, user_id: str) -> UserClipboardState:
        if user_id not in self._states:
            self._states[user_id] = UserClipboardState(user_id)
        return self._states[user_id]

    def update_clipboard(
        self,
        user_id: str,
        origin_device: str,
        text: str,
        content_hash: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        if not text:
            return False, "Empty clipboard text", None

        # Size cap: 100 KB
        text_bytes = text.encode("utf-8")
        if len(text_bytes) > settings.CLIPBOARD_MAX_SIZE_BYTES:
            return False, f"Clipboard content exceeds {settings.CLIPBOARD_MAX_SIZE_BYTES // 1024} KB limit", None

        # Compute hash
        calc_hash = hashlib.sha256(text_bytes).hexdigest()
        c_hash = (content_hash or calc_hash).lower()

        state = self.get_state(user_id)
        state.clean_old_hashes()

        now = time.time()
        # Loop prevention: drop duplicate if seen within dedup window
        if c_hash in state.recent_hashes:
            if now - state.recent_hashes[c_hash] < settings.CLIPBOARD_DEDUP_WINDOW_SECONDS:
                logger.info(f"Dropped duplicate clipboard update with hash {c_hash[:8]}")
                return False, "Duplicate clip within 5s window", None

        state.recent_hashes[c_hash] = now
        state.latest_clip = {
            "text": text,
            "hash": c_hash,
            "origin_device": origin_device,
            "timestamp": now
        }

        push_msg = {
            "type": "clipboard_push",
            "hash": c_hash,
            "text": text,
            "from_device": origin_device
        }
        return True, None, push_msg

    def get_latest_clip(self, user_id: str) -> Optional[Dict[str, Any]]:
        state = self.get_state(user_id)
        if state.is_clip_expired():
            return None
        return state.latest_clip

    async def fan_out_clipboard(self, user_id: str, origin_device: str, push_msg: Dict[str, Any]):
        devices = await registry.get_user_devices(user_id)
        for dev in devices:
            # Never send back to origin device (loop prevention)
            if dev.device_id != origin_device:
                try:
                    await dev.websocket.send_json(push_msg)
                except Exception as e:
                    logger.warning(f"Failed to push clipboard to {dev.device_id}: {e}")

clipboard_sync_manager = ClipboardSyncManager()
