from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

# REST schemas
class RegisterFirstDeviceRequest(BaseModel):
    device_name: str = Field(..., min_length=1)
    platform: str = Field(..., min_length=1)  # "android", "windows", etc.
    capabilities: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None

class DeviceAuthResponse(BaseModel):
    user_id: str
    device_id: str
    token: str

class PairStartResponse(BaseModel):
    code: str
    expires_at: datetime
    qr_payload: str
    qr_image: Optional[str] = None

class PairCompleteRequest(BaseModel):
    code: str = Field(..., min_length=1)
    device_name: str = Field(..., min_length=1)
    platform: str = Field(..., min_length=1)
    capabilities: List[str] = Field(default_factory=list)

class OnlineDeviceSchema(BaseModel):
    id: str
    name: str
    platform: str
    capabilities: List[str]

# WebSocket schemas
class WSHeartbeatMessage(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"

class WSCommandMessage(BaseModel):
    type: Literal["command"] = "command"
    id: str
    action: str
    target: str
    params: Dict[str, Any] = Field(default_factory=dict)

class WSResultMessage(BaseModel):
    type: Literal["result"] = "result"
    command_id: str
    status: Literal["ok", "error"]
    data: Dict[str, Any] = Field(default_factory=dict)

class WSExecuteMessage(BaseModel):
    type: Literal["execute"] = "execute"
    command_id: str
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    from_device: str

class WSCommandStatusMessage(BaseModel):
    type: Literal["command_status"] = "command_status"
    command_id: str
    status: Literal["delivered", "ok", "error", "offline"]
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

class WSDevicesMessage(BaseModel):
    type: Literal["devices"] = "devices"
    online: List[OnlineDeviceSchema]

# Phase 2: Text Commands & Confirmation schemas
class TextCommandRequest(BaseModel):
    text: str = Field(..., min_length=1)

class TextCommandResponse(BaseModel):
    status: Literal["executed", "clarify", "confirm_required", "failed", "unknown"]
    intent: Optional[Dict[str, Any]] = None
    question: Optional[str] = None
    missing_slots: Optional[List[str]] = None
    confirmation_id: Optional[str] = None
    prompt: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class ConfirmRequestPayload(BaseModel):
    confirmation_id: str = Field(..., min_length=1)

class CancelRequestPayload(BaseModel):
    confirmation_id: str = Field(..., min_length=1)

class WSConfirmRequestMessage(BaseModel):
    type: Literal["confirm_request"] = "confirm_request"
    confirmation_id: str
    skill: str
    target: str
    params: Dict[str, Any]
    prompt: str

class WSConfirmMessage(BaseModel):
    type: Literal["confirm"] = "confirm"
    confirmation_id: str

class WSCancelMessage(BaseModel):
    type: Literal["cancel"] = "cancel"
    confirmation_id: str

class WSClarifyMessage(BaseModel):
    type: Literal["clarify"] = "clarify"
    question: str
    missing_slots: List[str]

