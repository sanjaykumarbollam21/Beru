import math
import secrets
import logging
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header, status
from fastapi.responses import StreamingResponse
from hub.auth import get_current_device
from hub.db import Device
from hub.config import settings
from hub.registry import registry
from hub.transfer.models import (
    TransferStartRequest,
    TransferStartResponse,
    TransferStatusResponse,
    TransferRecord,
    utcnow
)
from hub.transfer.store import transfer_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transfer", tags=["transfer"])

@router.post("/start", response_model=TransferStartResponse)
async def start_transfer(
    payload: TransferStartRequest,
    current_device: Device = Depends(get_current_device)
):
    if payload.size > settings.TRANSFER_MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum limit of {settings.TRANSFER_MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB"
        )

    transfer_id = f"trf-{secrets.token_hex(8)}"
    upload_token = secrets.token_urlsafe(32)
    chunk_size = settings.TRANSFER_CHUNK_SIZE_BYTES
    total_chunks = max(1, math.ceil(payload.size / chunk_size))
    expires_at = utcnow() + timedelta(hours=settings.TRANSFER_EXPIRE_HOURS)

    record = TransferRecord(
        transfer_id=transfer_id,
        user_id=current_device.user_id,
        from_device_id=payload.from_device,
        to_device_id=payload.to_device,
        file_name=payload.name,
        file_size=payload.size,
        sha256=payload.sha256.lower(),
        mime=payload.mime or "application/octet-stream",
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        upload_token=upload_token,
        expires_at=expires_at
    )
    transfer_store.add_record(record)

    return TransferStartResponse(
        transfer_id=transfer_id,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        upload_token=upload_token,
        expires_at=expires_at
    )

@router.put("/{transfer_id}/chunk/{chunk_index}")
async def upload_chunk(
    transfer_id: str,
    chunk_index: int,
    request: Request,
    x_upload_token: Optional[str] = Header(None, alias="X-Upload-Token"),
    upload_token: Optional[str] = None
):
    record = transfer_store.get_record(transfer_id)
    if not record:
        raise HTTPException(status_code=404, detail="Transfer record not found")

    token = x_upload_token or upload_token
    if not token or token != record.upload_token:
        raise HTTPException(status_code=401, detail="Invalid upload token")

    if chunk_index < 0 or chunk_index >= record.total_chunks:
        raise HTTPException(status_code=400, detail="Chunk index out of range")

    raw_chunk = await request.body()
    if not raw_chunk:
        raise HTTPException(status_code=400, detail="Empty chunk body")

    transfer_store.save_chunk(transfer_id, chunk_index, raw_chunk)

    # Check if all chunks have been received
    if len(record.received_chunks) == record.total_chunks:
        verified, msg = transfer_store.assemble_and_verify(record)
        if not verified:
            raise HTTPException(status_code=400, detail=msg)

        # Notify recipient device via WebSocket if online
        target_device = await registry.resolve_target(
            user_id=record.user_id,
            sender_device_id=record.from_device_id,
            target=record.to_device_id
        )
        if target_device:
            try:
                await target_device.websocket.send_json({
                    "type": "file_ready",
                    "transfer_id": record.transfer_id,
                    "name": record.file_name,
                    "size": record.file_size,
                    "sha256": record.sha256,
                    "mime": record.mime,
                    "from_device": record.from_device_id
                })
            except Exception as e:
                logger.warning(f"Failed to send file_ready to {target_device.device_id}: {e}")

    return {
        "status": "ok",
        "transfer_id": transfer_id,
        "chunk_index": chunk_index,
        "received_chunks": sorted(list(record.received_chunks)),
        "is_complete": record.status == "ready"
    }

@router.get("/{transfer_id}/status", response_model=TransferStatusResponse)
async def get_transfer_status(
    transfer_id: str,
    current_device: Device = Depends(get_current_device)
):
    record = transfer_store.get_record(transfer_id)
    if not record or record.user_id != current_device.user_id:
        raise HTTPException(status_code=404, detail="Transfer not found")

    return record.to_status_response()

@router.get("/{transfer_id}/download")
async def download_file(
    transfer_id: str,
    request: Request,
    current_device: Device = Depends(get_current_device)
):
    record = transfer_store.get_record(transfer_id)
    if not record or record.user_id != current_device.user_id:
        raise HTTPException(status_code=404, detail="Transfer not found")

    if record.status not in ("ready", "delivered"):
        raise HTTPException(status_code=400, detail=f"Transfer not ready for download (status: {record.status})")

    file_size = record.file_size
    range_header = request.headers.get("Range")

    start_byte = 0
    end_byte = file_size - 1

    if range_header:
        # e.g. bytes=0-1048575 or bytes=1048576-
        try:
            unit, ranges = range_header.strip().split("=")
            if unit == "bytes":
                parts = ranges.split("-")
                if parts[0]:
                    start_byte = int(parts[0])
                if len(parts) > 1 and parts[1]:
                    end_byte = int(parts[1])
        except Exception:
            pass

    content_length = (end_byte - start_byte) + 1
    stream = transfer_store.get_decrypted_stream(
        record=record,
        start_byte=start_byte,
        length=content_length
    )

    headers = {
        "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Disposition": f'attachment; filename="{record.file_name}"',
        "Content-Type": record.mime or "application/octet-stream"
    }
    status_code = 206 if range_header else 200

    return StreamingResponse(
        stream,
        status_code=status_code,
        headers=headers
    )

@router.post("/{transfer_id}/ack")
async def acknowledge_transfer(
    transfer_id: str,
    current_device: Device = Depends(get_current_device)
):
    record = transfer_store.get_record(transfer_id)
    if not record or record.user_id != current_device.user_id:
        raise HTTPException(status_code=404, detail="Transfer not found")

    record.status = "delivered"
    record.delivered_at = utcnow()

    # Delete encrypted stored chunks immediately
    transfer_store.delete_transfer_data(transfer_id)

    # Notify sender that file was delivered
    sender = await registry.resolve_target(
        user_id=record.user_id,
        sender_device_id=current_device.id,
        target=record.from_device_id
    )
    if sender:
        try:
            await sender.websocket.send_json({
                "type": "file_ack",
                "transfer_id": transfer_id,
                "delivered_to": current_device.id
            })
        except Exception:
            pass

    return {"status": "delivered", "transfer_id": transfer_id}
