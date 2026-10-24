from typing import Optional
from pydantic import BaseModel, Field
from hub.skills.base import Skill, skill_registry

# --- set_alarm ---
class AlarmParams(BaseModel):
    time: str = Field(..., description="Time for alarm, e.g. 6 am or 07:30")
    label: Optional[str] = Field(None, description="Optional alarm label")

class SetAlarmSkill(Skill):
    name = "set_alarm"
    description = "Set an alarm for a given time on phone"
    parameters = AlarmParams
    supported_platforms = ["android"]
    default_target = "phone"
    confirmation = "none"
    action = "set_alarm"

# --- set_reminder ---
class ReminderParams(BaseModel):
    title: str = Field(..., description="Reminder title or task to remember")
    time: Optional[str] = Field(None, description="Time or date for reminder")

class SetReminderSkill(Skill):
    name = "set_reminder"
    description = "Set a task reminder or note with optional trigger time"
    parameters = ReminderParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "set_reminder"

def register_reminder_skills():
    skill_registry.register(SetAlarmSkill())
    skill_registry.register(SetReminderSkill())
