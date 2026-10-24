import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from hub.skills.base import Skill, skill_registry

logger = logging.getLogger(__name__)

class RememberParams(BaseModel):
    text: str = Field(..., description="Fact or note to remember (e.g. 'gym card is in the blue bag')")

class RememberSkill(Skill):
    name = "remember"
    description = "Remember a fact or personal note for the user"
    parameters = RememberParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "remember"

class ForgetParams(BaseModel):
    query: str = Field(..., description="Query or topic of facts to forget (or 'everything' to clear all)")

class ForgetSkill(Skill):
    name = "forget"
    description = "Forget a previously remembered fact or note (or forget everything)"
    parameters = ForgetParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"  # "hard" if forgetting everything
    action = "forget"

    def __init__(self):
        super().__init__()

class RecallParams(BaseModel):
    query: str = Field(..., description="Query or topic of facts to retrieve")

class RecallSkill(Skill):
    name = "recall"
    description = "Recall or retrieve remembered facts or notes"
    parameters = RecallParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "recall"

class ListPreferencesParams(BaseModel):
    pass

class ListPreferencesSkill(Skill):
    name = "list_preferences"
    description = "List all current user preferences, default targets, and settings"
    parameters = ListPreferencesParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "list_preferences"

class CreateRoutineParams(BaseModel):
    name: str = Field(..., description="Name of the routine (e.g. 'work mode')")
    steps: List[Dict[str, Any]] = Field(..., description="List of skill steps to execute")

class CreateRoutineSkill(Skill):
    name = "create_routine"
    description = "Create a saved multi-step routine"
    parameters = CreateRoutineParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "soft"
    action = "create_routine"

class RunRoutineParams(BaseModel):
    name: str = Field(..., description="Name of the routine to execute")

class RunRoutineSkill(Skill):
    name = "run_routine"
    description = "Run a saved multi-step routine by name"
    parameters = RunRoutineParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "run_routine"

class DeleteRoutineParams(BaseModel):
    name: str = Field(..., description="Name of the routine to delete")

class DeleteRoutineSkill(Skill):
    name = "delete_routine"
    description = "Delete a saved routine by name"
    parameters = DeleteRoutineParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "soft"
    action = "delete_routine"

def register_personal_skills():
    skill_registry.register(RememberSkill())
    skill_registry.register(ForgetSkill())
    skill_registry.register(RecallSkill())
    skill_registry.register(ListPreferencesSkill())
    skill_registry.register(CreateRoutineSkill())
    skill_registry.register(RunRoutineSkill())
    skill_registry.register(DeleteRoutineSkill())
