from typing import Literal, List, Dict, Type, Any, Optional, get_origin
from pydantic import BaseModel, ValidationError

ConfirmationLevel = Literal["none", "soft", "hard"]
DefaultTarget = Literal["self", "phone", "pc"]

class Skill:
    name: str
    description: str
    parameters: Type[BaseModel]
    supported_platforms: List[str]  # e.g. ["android", "windows"]
    default_target: DefaultTarget = "self"
    confirmation: ConfirmationLevel = "none"
    action: str = ""  # Device action to trigger, defaults to name if empty

    def get_action_name(self) -> str:
        return self.action or self.name

    def get_required_fields(self) -> List[str]:
        required = []
        for field_name, field_info in self.parameters.model_fields.items():
            if field_info.is_required():
                required.append(field_name)
        return required

    def get_missing_fields(self, data: Dict[str, Any]) -> List[str]:
        missing = []
        for req in self.get_required_fields():
            val = data.get(req)
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(req)
        return missing

    def validate_params(self, data: Dict[str, Any]) -> tuple[bool, Optional[BaseModel], Optional[str]]:
        try:
            instance = self.parameters(**data)
            return True, instance, None
        except ValidationError as e:
            return False, None, str(e)

    def to_llm_spec(self) -> Dict[str, Any]:
        props = {}
        required = []
        for name, field in self.parameters.model_fields.items():
            field_type = str(field.annotation) if field.annotation else "string"
            props[name] = {
                "type": field_type,
                "description": field.description or name
            }
            if field.is_required():
                required.append(name)
        return {
            "name": self.name,
            "description": self.description,
            "supported_platforms": self.supported_platforms,
            "default_target": self.default_target,
            "confirmation": self.confirmation,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required
            }
        }

class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill):
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_all(self) -> List[Skill]:
        return list(self._skills.values())

    def to_llm_specs(self) -> List[Dict[str, Any]]:
        return [skill.to_llm_spec() for skill in self._skills.values()]

skill_registry = SkillRegistry()
