from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, Type
from pydantic import BaseModel

class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Union[Type[BaseModel], Dict[str, Any]]] = None
    ) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        """
        Execute completion with the given messages.
        If schema is provided, return structured dict or list.
        """
        pass

class MockLLMProvider(LLMProvider):
    """
    Test/mock provider that returns programmed responses or simple heuristic fallbacks.
    """
    name = "mock"

    def __init__(self, responses: Optional[List[Any]] = None):
        self.responses: List[Any] = responses or []
        self.call_history: List[Dict[str, Any]] = []

    def set_response(self, response: Any):
        self.responses = [response]

    async def complete(
        self,
        messages: List[Dict[str, str]],
        schema: Optional[Union[Type[BaseModel], Dict[str, Any]]] = None
    ) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        self.call_history.append({"messages": messages, "schema": schema})
        if self.responses:
            res = self.responses.pop(0)
            if isinstance(res, Exception):
                raise res
            return res
        return {
            "skill": "lock_device",
            "params": {},
            "target": "pc",
            "confidence": 0.95
        }
