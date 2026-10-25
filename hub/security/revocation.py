import logging
from typing import List, Dict, Any, Optional
from datetime import timedelta
from sqlalchemy.orm import Session
from hub.db import Device, utcnow
from hub.auth import generate_device_token, hash_token
from hub.registry import registry
from hub.security.audit import audit_logger

logger = logging.getLogger(__name__)

async def revoke_device(db: Session, user_id: str, device_id: str) -> bool:
    """
    Revokes a device: marks it as revoked, invalidates its token,
    and immediately cuts off any active WebSocket connections.
    """
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.user_id == user_id
    ).first()

    if not device:
        logger.warning(f"Revoke failed: device {device_id} not found for user {user_id}")
        return False

    device.is_revoked = True
    # Scramble the token hash so existing tokens never match
    device.token_hash = hash_token(generate_device_token() + "_REVOKED")
    db.commit()

    # Immediately disconnect live connection if active
    await registry.disconnect_device(device_id, code=1008, reason="Device revoked")

    audit_logger.log_event(
        event_type="device_revoked",
        user_id=user_id,
        device_id=device_id,
        outcome="success"
    )
    logger.info(f"Device {device_id} for user {user_id} revoked and disconnected.")
    return True

def rotate_device_token(db: Session, user_id: str, device_id: str) -> Optional[str]:
    """
    Rotates a device's authentication token.
    Returns the new raw token to provide to the client.
    """
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.user_id == user_id
    ).first()

    if not device or device.is_revoked:
        return None

    new_raw_token = generate_device_token()
    device.token_hash = hash_token(new_raw_token)
    device.last_seen = utcnow()
    db.commit()

    audit_logger.log_event(
        event_type="token_rotated",
        user_id=user_id,
        device_id=device_id,
        outcome="success"
    )
    logger.info(f"Rotated token for device {device_id}")
    return new_raw_token

def list_user_devices(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """
    Lists all devices for a user, including revocation and last seen status.
    """
    devices = db.query(Device).filter(Device.user_id == user_id).all()
    results = []
    for d in devices:
        results.append({
            "id": d.id,
            "name": d.name,
            "platform": d.platform,
            "capabilities": d.capabilities,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "is_revoked": bool(d.is_revoked)
        })
    return results
