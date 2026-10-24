import io
import logging
from typing import Optional
from hub.voice.stt.base import STTProvider, pcm_to_wav_bytes

logger = logging.getLogger(__name__)

class LocalWhisperSTTProvider(STTProvider):
    name = "local_whisper"

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                logger.info("faster-whisper model loaded.")
            except ImportError:
                raise RuntimeError("faster-whisper is not installed for local STT")

    async def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        self._load_model()
        wav_bytes = pcm_to_wav_bytes(pcm_bytes, sample_rate=sample_rate)
        wav_io = io.BytesIO(wav_bytes)

        segments, _ = self._model.transcribe(wav_io, beam_size=1)
        transcript = " ".join([seg.text for seg in segments]).strip()
        return transcript
