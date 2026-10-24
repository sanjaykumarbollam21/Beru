import io
import base64
import secrets
import string
import uuid
from datetime import timedelta
import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from hub.db import get_db, utcnow, User, Device, PairingCode
from hub.config import settings
from hub.auth import generate_device_token, hash_token, get_current_device
from hub.schemas import (
    RegisterFirstDeviceRequest,
    DeviceAuthResponse,
    PairStartResponse,
    PairCompleteRequest,
)

router = APIRouter(tags=["pairing"])

def generate_pairing_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

@router.post("/register-first-device", response_model=DeviceAuthResponse)
def register_first_device(
    payload: RegisterFirstDeviceRequest,
    db: Session = Depends(get_db)
):
    if payload.user_id:
        user = db.query(User).filter(User.id == payload.user_id).first()
        if user:
            existing_device = db.query(Device).filter(Device.user_id == user.id).first()
            if existing_device:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="First device has already been registered for this user"
                )
        else:
            user = User(id=payload.user_id)
            db.add(user)
            db.flush()
    else:
        user = User(id=str(uuid.uuid4()))
        db.add(user)
        db.flush()

    raw_token = generate_device_token()
    token_h = hash_token(raw_token)

    device = Device(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name=payload.device_name,
        platform=payload.platform.lower(),
        token_hash=token_h,
        capabilities=payload.capabilities,
        last_seen=utcnow()
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    return DeviceAuthResponse(
        user_id=user.id,
        device_id=device.id,
        token=raw_token
    )

@router.post("/pair/start", response_model=PairStartResponse)
def pair_start(
    current_device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    code = generate_pairing_code(6)
    while db.query(PairingCode).filter(PairingCode.code == code).first() is not None:
        code = generate_pairing_code(6)

    expires_at = utcnow() + timedelta(seconds=settings.PAIRING_CODE_EXPIRE_SECONDS)
    pairing_code = PairingCode(
        code=code,
        user_id=current_device.user_id,
        expires_at=expires_at,
        used=False
    )
    db.add(pairing_code)
    db.commit()

    qr_payload = f"beru://pair?code={code}&hub={settings.HUB_BASE_URL}"

    # Generate QR image as base64 data URI
    qr_img = qrcode.make(qr_payload)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    b64_qr = base64.b64encode(buf.getvalue()).decode("utf-8")
    qr_data_uri = f"data:image/png;base64,{b64_qr}"

    return PairStartResponse(
        code=code,
        expires_at=expires_at,
        qr_payload=qr_payload,
        qr_image=qr_data_uri
    )

@router.post("/pair/complete", response_model=DeviceAuthResponse)
def pair_complete(
    payload: PairCompleteRequest,
    db: Session = Depends(get_db)
):
    pairing_record = db.query(PairingCode).filter(PairingCode.code == payload.code).first()
    if not pairing_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pairing code"
        )

    if pairing_record.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pairing code has already been used"
        )

    expires = pairing_record.expires_at
    if expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    if expires < utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pairing code has expired"
        )

    pairing_record.used = True

    raw_token = generate_device_token()
    token_h = hash_token(raw_token)

    device = Device(
        id=str(uuid.uuid4()),
        user_id=pairing_record.user_id,
        name=payload.device_name,
        platform=payload.platform.lower(),
        token_hash=token_h,
        capabilities=payload.capabilities,
        last_seen=utcnow()
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    return DeviceAuthResponse(
        user_id=pairing_record.user_id,
        device_id=device.id,
        token=raw_token
    )
