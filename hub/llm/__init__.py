import logging
from typing import List, Dict, Any, Optional, Union, Type
from pydantic import BaseModel
from hub.llm.provider import LLMProvider, MockLLMProvider
from hub.llm.groq import GroqProvider
from hub.llm.gemini import GeminiProvider
from hub.llm.ollama import OllamaProvider

logger = logging.getLogger(__name__)

class LLMOrchestrator:
    def __init__(self):
        self.mock_provider: Optional[MockLLMProvider] = None

    def get_providers_for_task(self, task_type: str = "intent") -> List[LLMProvider]:
        if self.mock_provider is not None:
            return [self.mock_provider]

        if task_type == "planning":
            # Gemini -> Groq -> Ollama
            return [GeminiProvider(), GroqProvider(), OllamaProvider()]
        else:
            # Intent parsing / quick dialog: Groq -> Gemini -> Ollama
            return [GroqProvider(), GeminiProvider(), OllamaProvider()]

    async def complete_with_fallback(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Union[Type[BaseModel], Dict[str, Any]]] = None,
        task_type: str = "intent",
        custom_providers: Optional[List[LLMProvider]] = None
    ) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        providers = custom_providers or self.get_providers_for_task(task_type)
        last_error = None

        import time
        from hub.reliability.breaker import circuit_registry
        from hub.reliability.health import metrics_collector

        for provider in providers:
            breaker = circuit_registry.get_breaker(provider.name)
            if not breaker.can_execute():
                logger.info(f"Skipping {provider.name}: circuit breaker is OPEN")
                continue

            start_t = time.time()
            try:
                logger.info(f"Attempting LLM completion with provider: {provider.name}")
                result = await provider.complete(messages, schema=schema)
                breaker.record_success()
                metrics_collector.record_llm_latency(time.time() - start_t)
                return result
            except Exception as e:
                breaker.record_failure()
                metrics_collector.record_provider_failure(provider.name)
                logger.warning(f"Provider {provider.name} failed: {e}. Falling back to next...")
                last_error = e

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

llm_orchestrator = LLMOrchestrator()

__all__ = [
    "LLMProvider",
    "MockLLMProvider",
    "GroqProvider",
    "GeminiProvider",
    "OllamaProvider",
    "LLMOrchestrator",
    "llm_orchestrator"
]
