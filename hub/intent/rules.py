import re
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from rapidfuzz import fuzz
from hub.skills.base import skill_registry

@dataclass
class RuleMatch:
    skill_name: str
    params: Dict[str, Any]
    explicit_target: Optional[str]
    confidence: float

def extract_explicit_target(text: str) -> Tuple[Optional[str], str]:
    """
    Extract target phrase like 'on my laptop', 'on phone', etc.
    Returns (target, cleaned_text).
    """
    target = None
    cleaned = text

    # PC / Laptop / Windows
    pc_match = re.search(r"\b(?:on\s+(?:my\s+)?(?:laptop|pc|computer|desktop|windows))\b", cleaned, re.IGNORECASE)
    if pc_match:
        target = "pc"
        cleaned = cleaned[:pc_match.start()] + cleaned[pc_match.end():]

    # Phone / Mobile / Android
    phone_match = re.search(r"\b(?:on\s+(?:my\s+)?(?:phone|mobile|android))\b", cleaned, re.IGNORECASE)
    if phone_match:
        target = "phone"
        cleaned = cleaned[:phone_match.start()] + cleaned[phone_match.end():]

    # Self / this device
    self_match = re.search(r"\b(?:on\s+this\s+device|locally|here)\b", cleaned, re.IGNORECASE)
    if self_match:
        target = "self"
        cleaned = cleaned[:self_match.start()] + cleaned[self_match.end():]

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return target, cleaned

def match_rules(text: str) -> Optional[RuleMatch]:
    raw_text = text.strip()
    if not raw_text:
        return None

    explicit_target, cleaned = extract_explicit_target(raw_text)
    lower = cleaned.lower().strip()

    # 1. lock_device
    if re.search(r"^(?:please\s+)?lock(?:\s+(?:the|my))?(?:\s+(?:screen|pc|laptop|computer|phone|device))?$", lower):
        # If user said "lock my pc", explicit target might be in raw_text or matched here
        if "phone" in lower:
            explicit_target = explicit_target or "phone"
        elif "pc" in lower or "laptop" in lower or "computer" in lower:
            explicit_target = explicit_target or "pc"
        return RuleMatch("lock_device", {}, explicit_target, 0.98)

    # 2. set_volume
    vol_match = re.search(r"(?:set\s+)?(?:the\s+)?volume\s+(?:to\s+)?(\d+)(?:%)?", lower)
    if vol_match:
        val = int(vol_match.group(1))
        return RuleMatch("set_volume", {"level": min(max(val, 0), 100)}, explicit_target, 0.95)
    
    vol_plain = re.search(r"^(?:set\s+)?volume$", lower)
    if vol_plain:
        return RuleMatch("set_volume", {}, explicit_target, 0.85)

    # 3. open_app
    open_match = re.search(r"^(?:open|launch|start)(?:\s+(?:the\s+)?app)?\s+([a-zA-Z0-9_\-\.\s]+)$", cleaned, re.IGNORECASE)
    if open_match:
        app_name = open_match.group(1).strip()
        if app_name.lower() not in ["flashlight", "alarm", "reminder"]:
            return RuleMatch("open_app", {"app_name": app_name}, explicit_target, 0.92)

    # 4. toggle_flashlight
    if re.search(r"(?:turn\s+on|enable)\s+(?:the\s+)?flashlight", lower) or lower == "flashlight on":
        return RuleMatch("toggle_flashlight", {"state": "on"}, explicit_target or "phone", 0.95)
    if re.search(r"(?:turn\s+off|disable)\s+(?:the\s+)?flashlight", lower) or lower == "flashlight off":
        return RuleMatch("toggle_flashlight", {"state": "off"}, explicit_target or "phone", 0.95)
    if "flashlight" in lower:
        return RuleMatch("toggle_flashlight", {"state": "toggle"}, explicit_target or "phone", 0.90)

    # 5. set_alarm
    alarm_match = re.search(r"(?:set\s+(?:an?\s+)?)?alarm\s+(?:for|at)\s+(.+)$", cleaned, re.IGNORECASE)
    if alarm_match:
        alarm_time = alarm_match.group(1).strip()
        return RuleMatch("set_alarm", {"time": alarm_time}, explicit_target or "phone", 0.95)
    wake_match = re.search(r"wake\s+me\s+up\s+at\s+(.+)$", cleaned, re.IGNORECASE)
    if wake_match:
        alarm_time = wake_match.group(1).strip()
        return RuleMatch("set_alarm", {"time": alarm_time}, explicit_target or "phone", 0.95)
    if lower == "set alarm" or lower == "set an alarm":
        return RuleMatch("set_alarm", {}, explicit_target or "phone", 0.85)

    # 6. set_reminder
    rem_match = re.search(r"remind\s+me\s+to\s+(.+?)(?:\s+(?:at|on|in)\s+(.+))?$", cleaned, re.IGNORECASE)
    if rem_match:
        title = rem_match.group(1).strip()
        t = rem_match.group(2).strip() if rem_match.group(2) else None
        return RuleMatch("set_reminder", {"title": title, "time": t}, explicit_target, 0.92)
    rem_plain = re.search(r"^(?:set\s+(?:a\s+)?)?reminder(?:\s+to\s+(.+))?$", cleaned, re.IGNORECASE)
    if rem_plain:
        title = rem_plain.group(1).strip() if rem_plain.group(1) else ""
        params = {"title": title} if title else {}
        return RuleMatch("set_reminder", params, explicit_target, 0.85)

    # 7. send_message
    msg_match1 = re.search(r"send\s+(?:a\s+)?message\s+to\s+([a-zA-Z0-9_\-\+]+)\s+(?:saying|that)\s+(.+)$", cleaned, re.IGNORECASE)
    if msg_match1:
        recipient = msg_match1.group(1).strip()
        body = msg_match1.group(2).strip()
        return RuleMatch("send_message", {"recipient": recipient, "message": body, "app": "whatsapp"}, explicit_target or "phone", 0.95)

    msg_match2 = re.search(r"(?:whatsapp|message)\s+([a-zA-Z0-9_\-\+]+)\s+(?:saying\s+)?(.+)$", cleaned, re.IGNORECASE)
    if msg_match2:
        recipient = msg_match2.group(1).strip()
        body = msg_match2.group(2).strip()
        return RuleMatch("send_message", {"recipient": recipient, "message": body, "app": "whatsapp"}, explicit_target or "phone", 0.92)

    msg_incomplete = re.search(r"^send\s+(?:a\s+)?message(?:\s+to\s+([a-zA-Z0-9_\-\+]+))?$", cleaned, re.IGNORECASE)
    if msg_incomplete:
        recipient = msg_incomplete.group(1).strip() if msg_incomplete.group(1) else ""
        params = {"recipient": recipient} if recipient else {}
        return RuleMatch("send_message", params, explicit_target or "phone", 0.85)


    # RapidFuzz fallback against skill names / aliases
    best_skill = None
    best_score = 0.0
    for skill in skill_registry.list_all():
        score = fuzz.ratio(lower, skill.name.replace("_", " "))
        if score > best_score:
            best_score = score
            best_skill = skill.name

    if best_skill and best_score >= 80:
        return RuleMatch(best_skill, {}, explicit_target, best_score / 100.0)

    return None
