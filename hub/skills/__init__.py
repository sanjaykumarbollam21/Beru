from hub.skills.base import Skill, SkillRegistry, skill_registry
from hub.skills.system import register_system_skills
from hub.skills.reminders import register_reminder_skills
from hub.skills.messaging import register_messaging_skills

def init_skills():
    register_system_skills()
    register_reminder_skills()
    register_messaging_skills()

# Initialize on import
init_skills()

__all__ = ["Skill", "SkillRegistry", "skill_registry", "init_skills"]
