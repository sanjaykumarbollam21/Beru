import logging
from typing import List, Optional
from hub.voice.stt.base import STTProvider, MockSTTProvider
from hub.voice.stt.groq_stt import GroqSTTProvider
from hub.voice.stt.local_whisper import LocalWhisperSTTProvider

logger = logging.getLogger(__name__)

class STTOrchestrator:
    def __init__(self):
        self.mock_provider: Optional[MockSTTProvider] = None

    def get_providers(self) -> List[STTProvider]:
        if self.mock_provider is not None:
            return [self.mock_provider]
        return [GroqSTTProvider(), LocalWhisperSTTProvider()]

    async def transcribe_with_fallback(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        custom_providers: Optional[List[STTProvider]] = None
    ) -> str:
        providers = custom_providers or self.get_providers()
        last_error = None

        import time
        from hub.reliability.breaker import circuit_registry
        from hub.reliability.health import metrics_collector

        for p in providers:
            breaker = circuit_registry.get_breaker(p.name)
            if not breaker.can_execute():
                logger.info(f"Skipping STT provider {p.name}: circuit breaker is OPEN")
                continue

            start_t = time.time()
            try:
                logger.info(f"Attempting STT transcription with provider: {p.name}")
                transcript = await p.transcribe(pcm_bytes, sample_rate=sample_rate)
                if transcript is not None:
                    breaker.record_success()
                    metrics_collector.record_stt_latency(time.time() - start_t)
                    return transcript
            except Exception as e:
                breaker.record_failure()
                metrics_collector.record_provider_failure(p.name)
                logger.warning(f"STT provider {p.name} failed: {e}. Trying fallback...")
                last_error = e

        raise RuntimeError(f"All STT providers failed. Last error: {last_error}")

stt_orchestrator = STTOrchestrator()

__all__ = [
    "STTProvider",
    "MockSTTProvider",
    "GroqSTTProvider",
    "LocalWhisperSTTProvider",
    "STTOrchestrator",
    "stt_orchestrator"
]
