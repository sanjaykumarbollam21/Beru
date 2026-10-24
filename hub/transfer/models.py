import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel, Field

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class TransferStartRequest(BaseModel):
    from_device: str = Field(..., min_length=1)
    to_device: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    size: int = Field(..., gt=0)
    sha256: str = Field(..., min_length=64, max_length=64)
    mime: Optional[str] = "application/octet-stream"

class TransferStartResponse(BaseModel):
    transfer_id: str
    chunk_size: int
    total_chunks: int
    upload_token: str
    expires_at: datetime

class TransferStatusResponse(BaseModel):
    transfer_id: str
    status: str  # pending, uploading, ready, delivered, failed, expired
    total_chunks: int
    received_chunks: List[int]
    is_complete: bool
    file_name: str
    file_size: int
    sha256: str

class TransferRecord:
    def __init__(
        self,
        transfer_id: str,
        user_id: str,
        from_device_id: str,
        to_device_id: str,
        file_name: str,
        file_size: int,
        sha256: str,
        mime: str,
        chunk_size: int,
        total_chunks: int,
        upload_token: str,
        expires_at: datetime
    ):
        self.transfer_id = transfer_id
        self.user_id = user_id
        self.from_device_id = from_device_id
        self.to_device_id = to_device_id
        self.file_name = file_name
        self.file_size = file_size
        self.sha256 = sha256
        self.mime = mime
        self.chunk_size = chunk_size
        self.total_chunks = total_chunks
        self.upload_token = upload_token
        self.status = "pending"
        self.created_at = utcnow()
        self.expires_at = expires_at
        self.delivered_at: Optional[datetime] = None
        self.received_chunks: set[int] = set()

    def is_expired(self) -> bool:
        return utcnow() > self.expires_at

    def to_status_response(self) -> TransferStatusResponse:
        return TransferStatusResponse(
            transfer_id=self.transfer_id,
            status=self.status,
            total_chunks=self.total_chunks,
            received_chunks=sorted(list(self.received_chunks)),
            is_complete=(len(self.received_chunks) == self.total_chunks and self.status in ("ready", "delivered")),
            file_name=self.file_name,
            file_size=self.file_size,
            sha256=self.sha256
        )
