import secrets
import hashlib
from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from hub.db import get_db, Device

security = HTTPBearer(auto_error=False)

def generate_device_token() -> str:
    return secrets.token_urlsafe(32)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def get_device_by_token(db: Session, token: str) -> Optional[Device]:
    if not token:
        return None
    token_h = hash_token(token)
    return db.query(Device).filter(Device.token_hash == token_h).first()

def get_current_device(
    auth: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db)
) -> Device:
    token: Optional[str] = None
    if auth:
        token = auth.credentials
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing device token"
        )
    
    device = get_device_by_token(db, token)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token"
        )
    return device
