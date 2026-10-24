import uuid
import time
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class WakeClaim(BaseModel):
    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str
    user_id: str
    detector_score: float = Field(..., ge=0.0, le=1.0)
    signal_level: float = Field(..., ge=0.0, le=1.0)
    screen_on: bool = False
    in_use: bool = False
    charging: bool = False
    received_at: float = Field(default_factory=time.time)

class WakeDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    winner_claim: Optional[WakeClaim] = None
    winner_device_id: Optional[str] = None
    runner_up_claim: Optional[WakeClaim] = None
    all_claims: List[WakeClaim] = Field(default_factory=list)
    scores: Dict[str, float] = Field(default_factory=dict)
    decided_at: float = Field(default_factory=time.time)
    reason: str = "score"
