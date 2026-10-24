import json
import logging
from typing import List, Dict, Any, Optional, Union, Type
import httpx
from pydantic import BaseModel
from hub.llm.provider import LLMProvider
from hub.config import settings

logger = logging.getLogger(__name__)

class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    async def complete(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Union[Type[BaseModel], Dict[str, Any]]] = None
    ) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1}
        }
        if schema is not None:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama API error {resp.status_code}: {resp.text}")
            data = resp.json()
            content = data.get("message", {}).get("content", "")

            if schema is not None:
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Failed to parse JSON from Ollama: {e}\nContent: {content}")
            return content
