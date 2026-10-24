from typing import Optional, Literal
from pydantic import BaseModel, Field
from hub.skills.base import Skill, skill_registry

# --- lock_device ---
class LockParams(BaseModel):
    force: bool = False
    message: Optional[str] = None

class LockDeviceSkill(Skill):
    name = "lock_device"
    description = "Lock the screen or secure workstation/phone"
    parameters = LockParams
    supported_platforms = ["windows", "android"]
    default_target = "pc"
    confirmation = "hard"
    action = "lock"

# --- set_volume ---
class VolumeParams(BaseModel):
    level: int = Field(..., ge=0, le=100, description="Volume level from 0 to 100")

class SetVolumeSkill(Skill):
    name = "set_volume"
    description = "Set the media/system volume percentage (0 to 100)"
    parameters = VolumeParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "volume"

# --- open_app ---
class OpenAppParams(BaseModel):
    app_name: str = Field(..., min_length=1, description="Name of application to open")

class OpenAppSkill(Skill):
    name = "open_app"
    description = "Launch or open an application by name"
    parameters = OpenAppParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "open_app"

# --- toggle_flashlight ---
class FlashlightParams(BaseModel):
    state: Literal["on", "off", "toggle"] = "toggle"

class ToggleFlashlightSkill(Skill):
    name = "toggle_flashlight"
    description = "Toggle or turn phone flashlight on or off"
    parameters = FlashlightParams
    supported_platforms = ["android"]
    default_target = "phone"
    confirmation = "none"
    action = "flashlight"

def register_system_skills():
    skill_registry.register(LockDeviceSkill())
    skill_registry.register(SetVolumeSkill())
    skill_registry.register(OpenAppSkill())
    skill_registry.register(ToggleFlashlightSkill())
