from abc import ABC, abstractmethod
from typing import Optional

class TTSProvider(ABC):
    name: str

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to 16kHz 16-bit PCM or WAV audio bytes."""
        pass

class MockTTSProvider(TTSProvider):
    name = "mock_tts"

    async def synthesize(self, text: str) -> bytes:
        # Return 0.2s of silent 16kHz 16-bit mono audio (6400 bytes)
        return b"\x00" * 6400
