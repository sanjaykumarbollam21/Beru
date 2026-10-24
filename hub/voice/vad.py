import io
import time
import struct
import logging
from typing import Tuple, Optional
import numpy as np
from hub.config import settings

logger = logging.getLogger(__name__)

class VADDetector:
    def __init__(
        self,
        sample_rate: int = settings.SAMPLE_RATE,
        speech_threshold: float = 0.5,
        silence_timeout_ms: int = settings.VAD_SILENCE_TIMEOUT_MS,
        initial_timeout_sec: float = settings.VAD_INITIAL_SPEECH_TIMEOUT_SEC,
        hard_cap_sec: float = settings.VOICE_HARD_CAP_SEC
    ):
        self.sample_rate = sample_rate
        self.speech_threshold = speech_threshold
        self.silence_timeout_ms = silence_timeout_ms
        self.initial_timeout_sec = initial_timeout_sec
        self.hard_cap_sec = hard_cap_sec

        self.model = None
        self._init_model()

        self.reset()

    def _init_model(self):
        try:
            import silero_vad
            self.model = silero_vad.load_silero_vad()
            logger.info("Silero VAD model loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load Silero VAD model ({e}); falling back to energy VAD.")
            self.model = None

    def reset(self):
        self.start_time = time.time()
        self.has_speech = False
        self.speech_start_time = None
        self.silence_start_time = None
        self.consecutive_silence_ms = 0.0
        self.audio_buffer = bytearray()
        if self.model and hasattr(self.model, "reset_states"):
            try:
                self.model.reset_states()
            except Exception:
                pass

    def _calculate_energy(self, pcm_chunk: bytes) -> float:
        if not pcm_chunk:
            return 0.0
        count = len(pcm_chunk) // 2
        shorts = struct.unpack(f"<{count}h", pcm_chunk)
        samples = np.array(shorts, dtype=np.float32) / 32768.0
        return float(np.sqrt(np.mean(samples ** 2)))

    def is_speech_chunk(self, pcm_chunk: bytes) -> bool:
        if len(pcm_chunk) < 64:
            return False

        energy = self._calculate_energy(pcm_chunk)

        if self.model is not None:
            try:
                import torch
                count = len(pcm_chunk) // 2
                shorts = struct.unpack(f"<{count}h", pcm_chunk)
                tensor = torch.tensor(shorts, dtype=torch.float32) / 32768.0

                # Silero VAD prefers 512 samples for 16kHz
                if len(tensor) < 512:
                    padding = torch.zeros(512 - len(tensor), dtype=torch.float32)
                    tensor = torch.cat([tensor, padding])
                elif len(tensor) > 512:
                    tensor = tensor[:512]

                speech_prob = float(self.model(tensor, self.sample_rate).item())
                if speech_prob >= self.speech_threshold:
                    return True
                if energy >= 0.08:
                    return True
                return False
            except Exception:
                pass

        # Fallback energy calculation
        return energy >= 0.015


    def process_frame(self, pcm_frame: bytes) -> Tuple[str, float]:
        """
        Process a chunk of 16-bit 16kHz PCM audio.
        Returns (status, speech_prob_or_energy)
        Statuses:
          - "listening": still collecting audio
          - "endpoint_detected": speech detected followed by ~800ms silence
          - "no_speech": 5s passed with no speech detected
          - "hard_cap": 15s maximum duration reached
        """
        self.audio_buffer.extend(pcm_frame)
        now = time.time()
        elapsed = now - self.start_time

        # 1. Hard cap reached
        if elapsed >= self.hard_cap_sec:
            return "hard_cap", 0.0

        # Calculate chunk duration in ms
        frame_duration_ms = (len(pcm_frame) / (2 * self.sample_rate)) * 1000.0
        is_speech = self.is_speech_chunk(pcm_frame)

        if is_speech:
            if not self.has_speech:
                self.has_speech = True
                self.speech_start_time = now
            self.consecutive_silence_ms = 0.0
            self.silence_start_time = None
        else:
            if self.has_speech:
                self.consecutive_silence_ms += frame_duration_ms

                # 2. Endpoint detected: speech followed by silence
                if self.consecutive_silence_ms >= self.silence_timeout_ms:
                    return "endpoint_detected", 0.0
            else:
                # 3. No speech detected within initial timeout
                if elapsed >= self.initial_timeout_sec:
                    return "no_speech", 0.0

        return "listening", 1.0 if is_speech else 0.0

    def get_audio_bytes(self) -> bytes:
        return bytes(self.audio_buffer)
