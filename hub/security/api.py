import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from hub.db import get_db, Device
from hub.auth import get_current_device
from hub.security.tickets import ticket_manager
from hub.security.revocation import revoke_device, rotate_device_token, list_user_devices
from hub.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["security"])

@router.post("/auth/ticket")
def create_websocket_ticket(
    current_device: Device = Depends(get_current_device)
):
    """
    Issues a short-lived (30s), single-use WebSocket ticket.
    Replaces long-lived auth tokens in URL query strings.
    """
    ticket = ticket_manager.create_ticket(
        device_id=current_device.id,
        user_id=current_device.user_id,
        ttl_seconds=settings.WS_TICKET_EXPIRE_SECONDS
    )
    return {
        "ticket": ticket,
        "expires_in": settings.WS_TICKET_EXPIRE_SECONDS
    }

@router.get("/devices")
def get_user_devices(
    current_device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """
    Lists paired devices for the current user.
    """
    devices = list_user_devices(db, current_device.user_id)
    return {"devices": devices}

@router.delete("/devices/{device_id}")
async def revoke_paired_device(
    device_id: str,
    current_device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """
    Immediately revokes a paired device, invalidates its credentials,
    and terminates its active WebSocket connections.
    """
    success = await revoke_device(db, current_device.user_id, device_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found or not owned by user"
        )
    return {"status": "revoked", "device_id": device_id}

@router.post("/devices/{device_id}/rotate-token")
def rotate_token_endpoint(
    device_id: str,
    current_device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """
    Rotates the authentication token for a device.
    """
    new_token = rotate_device_token(db, current_device.user_id, device_id)
    if not new_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found or revoked"
        )
    return {
        "device_id": device_id,
        "new_token": new_token
    }
