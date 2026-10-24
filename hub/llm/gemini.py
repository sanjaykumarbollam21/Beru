import json
import logging
from typing import List, Dict, Any, Optional, Union, Type
import httpx
from pydantic import BaseModel
from hub.llm.provider import LLMProvider
from hub.config import settings

logger = logging.getLogger(__name__)

class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model

    async def complete(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Union[Type[BaseModel], Dict[str, Any]]] = None
    ) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        if not self.api_key:
            raise ValueError("Gemini API key not configured")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        # Convert chat messages to Gemini contents format
        contents = []
        system_instruction = None
        for m in messages:
            role = m["role"]
            content = m["content"]
            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": content}]})

        body: Dict[str, Any] = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = system_instruction

        gen_config: Dict[str, Any] = {"temperature": 0.1}
        if schema is not None:
            gen_config["responseMimeType"] = "application/json"
        body["generationConfig"] = gen_config

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text}")
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned from Gemini")
            text = candidates[0]["content"]["parts"][0]["text"]

            if schema is not None:
                try:
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Failed to parse JSON from Gemini: {e}\nText: {text}")
            return text
