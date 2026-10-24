from typing import Optional
from pydantic import BaseModel, Field
from hub.skills.base import Skill, skill_registry

class CopyToDeviceParams(BaseModel):
    text: str = Field(..., min_length=1, description="Clipboard text content to copy across")
    target_device: Optional[str] = Field(None, description="Target device to receive clipboard content")

class CopyToDeviceSkill(Skill):
    name = "copy_to_device"
    description = "Copy text or link directly to another paired device's clipboard"
    parameters = CopyToDeviceParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "copy_to_device"

class PasteFromDeviceParams(BaseModel):
    source_device: Optional[str] = Field(None, description="Source device to retrieve clipboard from")

class PasteFromDeviceSkill(Skill):
    name = "paste_from_device"
    description = "Retrieve and paste clipboard content from another device"
    parameters = PasteFromDeviceParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "paste_from_device"

def register_clipboard_skills():
    skill_registry.register(CopyToDeviceSkill())
    skill_registry.register(PasteFromDeviceSkill())
