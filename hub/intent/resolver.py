import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from hub.skills.base import Skill, skill_registry
from hub.intent.rules import match_rules, RuleMatch, extract_explicit_target
from hub.intent.llm_router import llm_router, is_multi_step_request
from hub.config import settings

logger = logging.getLogger(__name__)

PLATFORM_MAP = {
    "pc": "windows",
    "laptop": "windows",
    "computer": "windows",
    "windows": "windows",
    "phone": "android",
    "mobile": "android",
    "android": "android"
}

@dataclass
class ResolvedIntent:
    skill: Skill
    params: Dict[str, Any]
    target_platform: str
    target_device: str  # "windows", "android", "self", or device_id
    confidence: float
    missing_slots: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_level: str = "none"
    error: Optional[str] = None

def resolve_target_platform(
    explicit_target: Optional[str],
    default_target: str,
    sender_platform: str
) -> str:
    """
    Target resolution priority:
    1. Explicit target wins
    2. Skill's default_target
    3. Sender device platform
    """
    if explicit_target:
        norm = explicit_target.lower().strip()
        if norm in PLATFORM_MAP:
            return PLATFORM_MAP[norm]
        if norm == "self":
            return sender_platform.lower()
        return norm

    if default_target:
        norm = default_target.lower().strip()
        if norm in PLATFORM_MAP:
            return PLATFORM_MAP[norm]
        if norm == "self":
            return sender_platform.lower()
        return norm

    return sender_platform.lower()

class IntentResolver:
    async def resolve(
        self,
        text: str,
        sender_platform: str = "android",
        sender_device_id: Optional[str] = None,
        context_intent: Optional[ResolvedIntent] = None
    ) -> List[ResolvedIntent]:
        raw_text = text.strip()
        if not raw_text:
            return []

        # Check follow-up context e.g. "do the same on my laptop", "again on windows"
        if context_intent and re.search(r"\b(?:do\s+the\s+same|same\s+thing|again|repeat)\b", raw_text, re.IGNORECASE):
            explicit_target, _ = extract_explicit_target(raw_text)
            target_platform = resolve_target_platform(
                explicit_target=explicit_target,
                default_target=context_intent.skill.default_target,
                sender_platform=sender_platform
            )
            return [
                self._build_resolved_intent(
                    skill=context_intent.skill,
                    params=dict(context_intent.params),
                    target_platform=target_platform,
                    target_device=explicit_target or context_intent.skill.default_target,
                    confidence=0.95
                )
            ]

        # Multi-step requests bypass single rule match
        if not is_multi_step_request(raw_text):
            # 1. Rules first
            rule_match: Optional[RuleMatch] = match_rules(raw_text)
            if rule_match and rule_match.confidence >= settings.INTENT_CONFIDENCE_THRESHOLD:
                skill = skill_registry.get(rule_match.skill_name)
                if skill:
                    target_platform = resolve_target_platform(
                        explicit_target=rule_match.explicit_target,
                        default_target=skill.default_target,
                        sender_platform=sender_platform
                    )
                    intent = self._build_resolved_intent(
                        skill=skill,
                        params=rule_match.params,
                        target_platform=target_platform,
                        target_device=target_platform,
                        confidence=rule_match.confidence
                    )
                    return [intent]

        # 2. LLM fallback
        logger.info(f"Falling back to LLM router for: '{raw_text}'")
        llm_steps = await llm_router.parse_intent(raw_text)
        if not llm_steps:
            # Fall back to best rule match if available
            rule_match = match_rules(raw_text)
            if rule_match:
                skill = skill_registry.get(rule_match.skill_name)
                if skill:
                    target_platform = resolve_target_platform(
                        explicit_target=rule_match.explicit_target,
                        default_target=skill.default_target,
                        sender_platform=sender_platform
                    )
                    return [
                        self._build_resolved_intent(
                            skill=skill,
                            params=rule_match.params,
                            target_platform=target_platform,
                            target_device=target_platform,
                            confidence=rule_match.confidence
                        )
                    ]
            return []

        resolved_plan = []
        for step in llm_steps:
            skill_name = step.get("skill")
            skill = skill_registry.get(skill_name) if skill_name else None
            if not skill:
                continue

            params = step.get("params", {})
            explicit_target = step.get("target")
            confidence = float(step.get("confidence", 0.8))

            target_platform = resolve_target_platform(
                explicit_target=explicit_target,
                default_target=skill.default_target,
                sender_platform=sender_platform
            )

            intent = self._build_resolved_intent(
                skill=skill,
                params=params,
                target_platform=target_platform,
                target_device=target_platform,
                confidence=confidence
            )
            resolved_plan.append(intent)


        return resolved_plan

    def _build_resolved_intent(
        self,
        skill: Skill,
        params: Dict[str, Any],
        target_platform: str,
        target_device: str,
        confidence: float
    ) -> ResolvedIntent:
        # Check platform support
        error = None
        if target_platform not in [p.lower() for p in skill.supported_platforms]:
            error = f"Platform '{target_platform}' does not support skill '{skill.name}'"

        # Check missing slots
        missing_slots = skill.get_missing_fields(params) if not error else []

        requires_confirm = skill.confirmation in ("soft", "hard")

        return ResolvedIntent(
            skill=skill,
            params=params,
            target_platform=target_platform,
            target_device=target_device,
            confidence=confidence,
            missing_slots=missing_slots,
            requires_confirmation=requires_confirm,
            confirmation_level=skill.confirmation,
            error=error
        )

intent_resolver = IntentResolver()
