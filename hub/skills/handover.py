from typing import Optional
from pydantic import BaseModel, Field
from hub.skills.base import Skill, skill_registry

class ContinueOnDeviceParams(BaseModel):
    target_device: Optional[str] = Field(None, description="Target device to continue task on (e.g. laptop, phone)")
    context_type: Optional[str] = Field("conversation", description="Context type: conversation, link, plan, or app")

class ContinueOnDeviceSkill(Skill):
    name = "continue_on_device"
    description = "Seamlessly hand over the current conversation, task plan, or link to another paired device"
    parameters = ContinueOnDeviceParams
    supported_platforms = ["windows", "android"]
    default_target = "pc"
    confirmation = "none"
    action = "continue_on_device"

def register_handover_skills():
    skill_registry.register(ContinueOnDeviceSkill())
