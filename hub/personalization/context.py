import logging
from typing import Dict, List, Optional, Any
from hub.config import settings
from hub.personalization.store import preference_store

logger = logging.getLogger(__name__)

class ContextBuilder:
    """
    Selects only the preferences and facts strictly relevant to the current user prompt.
    Enforces a hard cap on injected context characters (max ~500 tokens).
    """

    def build_context(self, user_id: str, prompt: str) -> str:
        prompt_lower = prompt.lower()
        prompt_words = set(prompt_lower.split())

        relevant_lines: List[str] = []

        # 1. Device aliases matching words in prompt
        aliases = preference_store.get_preference(user_id, "device_aliases", {})
        if isinstance(aliases, dict):
            matched_aliases = {k: v for k, v in aliases.items() if k in prompt_lower}
            if matched_aliases:
                relevant_lines.append(f"Device Aliases: {matched_aliases}")

        # 2. Preferred apps matching prompt keywords (e.g. music, browser, notes, spotify)
        apps = preference_store.get_preference(user_id, "preferred_apps", {})
        if isinstance(apps, dict):
            matched_apps = {k: v for k, v in apps.items() if k in prompt_lower or v.lower() in prompt_lower}
            if matched_apps:
                relevant_lines.append(f"Preferred Apps: {matched_apps}")

        # 3. Contact nicknames matching prompt
        contacts = preference_store.get_preference(user_id, "contacts", {})
        if isinstance(contacts, dict):
            matched_contacts = {k: v for k, v in contacts.items() if k in prompt_words}
            if matched_contacts:
                relevant_lines.append(f"Contacts: {matched_contacts}")

        # 4. Default targets for skills if relevant
        defaults = preference_store.get_preference(user_id, "default_targets", {})
        if isinstance(defaults, dict) and defaults:
            relevant_lines.append(f"Default Targets: {defaults}")

        # 5. Search facts relevant to prompt keywords
        facts = preference_store.search_facts(user_id, prompt)
        if facts:
            top_facts = [f["text"] for f in facts[:3]]
            relevant_lines.append(f"Remembered Facts: {top_facts}")

        if not relevant_lines:
            return ""

        context_str = "User Context:\n" + "\n".join(f"- {line}" for line in relevant_lines)

        # Enforce hard token/character cap
        max_chars = settings.CONTEXT_INJECTION_MAX_CHARS
        if len(context_str) > max_chars:
            context_str = context_str[:max_chars] + "..."

        return context_str

context_builder = ContextBuilder()
