import logging
from typing import Optional
import httpx
from hub.voice.stt.base import STTProvider, pcm_to_wav_bytes
from hub.config import settings

logger = logging.getLogger(__name__)

class GroqSTTProvider(STTProvider):
    name = "groq"

    def __init__(self, api_key: Optional[str] = None, model: str = "whisper-large-v3-turbo"):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = model
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        if not self.api_key:
            raise ValueError("Groq API key is not configured for STT")

        wav_bytes = pcm_to_wav_bytes(pcm_bytes, sample_rate=sample_rate)

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav")
        }
        data = {
            "model": self.model,
            "response_format": "json"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.url, headers=headers, files=files, data=data)
            if resp.status_code != 200:
                raise RuntimeError(f"Groq STT error {resp.status_code}: {resp.text}")
            result = resp.json()
            return result.get("text", "").strip()
