from typing import Optional
from hub.voice.tts.base import TTSProvider, MockTTSProvider
from hub.voice.tts.piper_tts import PiperTTSProvider

class TTSOrchestrator:
    def __init__(self):
        self.mock_provider: Optional[MockTTSProvider] = None

    def get_provider(self) -> TTSProvider:
        if self.mock_provider is not None:
            return self.mock_provider
        return PiperTTSProvider()

    async def synthesize(self, text: str) -> bytes:
        provider = self.get_provider()
        return await provider.synthesize(text)

tts_orchestrator = TTSOrchestrator()

__all__ = [
    "TTSProvider",
    "MockTTSProvider",
    "PiperTTSProvider",
    "TTSOrchestrator",
    "tts_orchestrator"
]
