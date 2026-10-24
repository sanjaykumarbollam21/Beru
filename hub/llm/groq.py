import json
import logging
from typing import List, Dict, Any, Optional, Union, Type
import httpx
from pydantic import BaseModel
from hub.llm.provider import LLMProvider
from hub.config import settings

logger = logging.getLogger(__name__)

class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    async def complete(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Union[Type[BaseModel], Dict[str, Any]]] = None
    ) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        if not self.api_key:
            raise ValueError("Groq API key not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1
        }

        if schema is not None:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.base_url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text}")
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            if schema is not None:
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Failed to parse JSON from Groq: {e}\nContent: {content}")
            return content
