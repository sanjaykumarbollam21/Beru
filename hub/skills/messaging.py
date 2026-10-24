from typing import Optional
from pydantic import BaseModel, Field
from hub.skills.base import Skill, skill_registry

class MessageParams(BaseModel):
    recipient: str = Field(..., min_length=1, description="Recipient contact name or phone number")
    message: str = Field(..., min_length=1, description="Message body or text")
    app: str = Field(default="whatsapp", description="Messaging service, e.g. whatsapp, sms")

class SendMessageSkill(Skill):
    name = "send_message"
    description = "Send a text message or WhatsApp message to a contact"
    parameters = MessageParams
    supported_platforms = ["android"]
    default_target = "phone"
    confirmation = "hard"
    action = "send_message"

def register_messaging_skills():
    skill_registry.register(SendMessageSkill())
