import io
import wave
from abc import ABC, abstractmethod
from typing import Optional, List

def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000, num_channels: int = 1, sampwidth: int = 2) -> bytes:
    """Convert raw PCM audio bytes to a complete WAV file in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()

class STTProvider(ABC):
    name: str

    @abstractmethod
    async def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        """Transcribe raw PCM audio to text."""
        pass

class MockSTTProvider(STTProvider):
    name = "mock_stt"

    def __init__(self, default_transcript: str = "lock my pc"):
        self.transcripts: List[str] = [default_transcript]
        self.call_count: int = 0

    def set_transcript(self, transcript: str):
        self.transcripts = [transcript]

    async def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        self.call_count += 1
        if self.transcripts:
            return self.transcripts.pop(0)
        return "Hey Beru, lock my pc"
