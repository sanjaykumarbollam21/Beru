from typing import Optional
from pydantic import BaseModel, Field
from hub.skills.base import Skill, skill_registry

# Executable and archive extensions requiring 'hard' confirmation
HARD_CONFIRM_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".msi", ".sh", ".ps1", ".vbs",
    ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z", ".iso"
}

class FindFileParams(BaseModel):
    query: str = Field(..., min_length=1, description="File name or search phrase (e.g. 'resume PDF')")
    device: Optional[str] = Field(None, description="Target device to search on")

class FindFileSkill(Skill):
    name = "find_file"
    description = "Search approved local folders on a device for a file by name or type"
    parameters = FindFileParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "none"
    action = "find_file"

class SendFileParams(BaseModel):
    query: str = Field(..., min_length=1, description="File name or search query to send")
    from_device: Optional[str] = Field(None, description="Source device holding the file")
    to_device: Optional[str] = Field(None, description="Destination device to receive the file")

class SendFileSkill(Skill):
    name = "send_file"
    description = "Find and transfer a file across paired devices"
    parameters = SendFileParams
    supported_platforms = ["windows", "android"]
    default_target = "self"
    confirmation = "soft"
    action = "send_file"

    def get_confirmation_level(self, params: dict) -> str:
        query = params.get("query", "").lower()
        if any(query.endswith(ext) or f"{ext} " in query for ext in HARD_CONFIRM_EXTENSIONS):
            return "hard"
        return "soft"

def register_file_skills():
    skill_registry.register(FindFileSkill())
    skill_registry.register(SendFileSkill())
