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
