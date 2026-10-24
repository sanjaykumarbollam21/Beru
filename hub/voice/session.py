import re
import time
import uuid
import logging
from typing import Optional, List, Dict, Any, Tuple
from hub.voice.vad import VADDetector
from hub.config import settings

logger = logging.getLogger(__name__)

def strip_wake_phrase(text: str, assistant_name: str = settings.ASSISTANT_NAME) -> str:
    cleaned = text.strip()
    name = assistant_name.lower()
    patterns = [
        rf"^(?:hey|ok|hi|hello)\s+{name}[,\.\s!]*",
        rf"^{name}[,\.\s!]*"
    ]
    for p in patterns:
        cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned

def classify_spoken_confirmation(text: str) -> Optional[bool]:
    lower = text.strip().lower()
    yes_terms = {"yes", "yeah", "yep", "confirm", "go ahead", "sure", "ok", "okay", "do it", "please"}
    no_terms = {"no", "nope", "cancel", "stop", "nevermind", "never mind", "abort", "dont", "don't"}

    words = re.findall(r"\b[\w']+\b", lower)
    if any(w in yes_terms for w in words):
        return True
    if any(w in no_terms for w in words):
        return False
    return None

class VoiceSession:
    def __init__(self, user_id: str, device_id: str, mode: str = "wake_word"):
        self.session_id: str = f"vses-{uuid.uuid4().hex[:8]}"
        self.user_id: str = user_id
        self.device_id: str = device_id
        self.mode: str = mode
        self.state: str = "idle"  # "listening", "thinking", "speaking", "waiting_for_voice_answer"
        self.vad = VADDetector()
        self.pending_confirmation_id: Optional[str] = None
        self.waiting_for_confirmation: bool = False
        self.waiting_for_clarification: bool = False
        self.reprompt_count: int = 0
        self.created_at: float = time.time()
        self.last_transcript: str = ""

    def start_listening(self):
        self.state = "listening"
        self.vad.reset()

    def add_audio_frame(self, pcm_frame: bytes) -> Tuple[str, float]:
        return self.vad.process_frame(pcm_frame)

    def get_audio_bytes(self) -> bytes:
        return self.vad.get_audio_bytes()

    def set_pending_confirmation(self, confirmation_id: str):
        self.pending_confirmation_id = confirmation_id
        self.waiting_for_confirmation = True
        self.waiting_for_clarification = False
        self.reprompt_count = 0

    def set_pending_clarification(self):
        self.waiting_for_clarification = True
        self.waiting_for_confirmation = False
        self.pending_confirmation_id = None
        self.reprompt_count = 0

    def clear_pending(self):
        self.pending_confirmation_id = None
        self.waiting_for_confirmation = False
        self.waiting_for_clarification = False
        self.reprompt_count = 0

class VoiceSessionManager:
    def __init__(self):
        self._sessions: Dict[str, VoiceSession] = {}

    def get_or_create(self, user_id: str, device_id: str, mode: str = "wake_word") -> VoiceSession:
        key = f"{user_id}:{device_id}"
        if key not in self._sessions:
            self._sessions[key] = VoiceSession(user_id, device_id, mode)
        return self._sessions[key]

    def remove(self, user_id: str, device_id: str):
        key = f"{user_id}:{device_id}"
        self._sessions.pop(key, None)

voice_session_manager = VoiceSessionManager()
