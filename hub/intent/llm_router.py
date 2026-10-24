import json
import re
import logging
from typing import List, Dict, Any, Optional
from hub.skills.base import skill_registry
from hub.llm import llm_orchestrator

logger = logging.getLogger(__name__)

def is_multi_step_request(text: str) -> bool:
    lower = text.lower()
    patterns = [
        r"\b(?:and\s+then|and\s+also|then|after\s+that)\b",
        r";\s*",
        r"\b(?:first\s+.+?\s+then\s+.+)\b"
    ]
    return any(re.search(p, lower) for p in patterns)

class LLMRouter:
    def __init__(self):
        pass

    async def parse_intent(self, text: str) -> List[Dict[str, Any]]:
        is_multi = is_multi_step_request(text)
        task_type = "planning" if is_multi else "intent"

        skills_spec = skill_registry.to_llm_specs()

        system_prompt = (
            "You are the intent router for Beru, an intelligent cross-device assistant.\n"
            "Given a user command, select the appropriate skill, extract parameters, and detect any target device.\n"
            f"Available skills:\n{json.dumps(skills_spec, indent=2)}\n\n"
            "Respond ONLY with a JSON object. If the request is a single step, return:\n"
            '{"steps": [{"skill": "<skill_name>", "params": {<extracted parameters>}, "target": "<pc|phone|self|null>", "confidence": 0.95}]}\n'
            "If the request is multi-step, return each step in order under 'steps'.\n"
            "If no skill matches, return: {\"steps\": []}."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]

        try:
            result = await llm_orchestrator.complete_with_fallback(
                messages=messages,
                schema={"type": "object"},
                task_type=task_type
            )
            if isinstance(result, str):
                result = json.loads(result)

            if isinstance(result, dict):
                if "steps" in result and isinstance(result["steps"], list):
                    return result["steps"]
                # In case LLM returned a single step dict directly
                if "skill" in result:
                    return [result]
            elif isinstance(result, list):
                return result

            return []
        except Exception as e:
            logger.error(f"LLM router failed: {e}")
            return []

llm_router = LLMRouter()
