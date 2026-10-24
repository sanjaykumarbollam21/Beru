import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.orm import Session
from hub.db import SessionLocal, utcnow, Device
from hub.auth import get_device_by_token
from hub.registry import registry
from hub.router import command_router
from hub.schemas import WSCommandMessage, WSResultMessage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
        return

    # Authenticate token against SQLite
    with SessionLocal() as db:
        device = get_device_by_token(db, token)
        if not device:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
            return
        
        device_id = device.id
        user_id = device.user_id
        device_name = device.name
        device_platform = device.platform
        capabilities = list(device.capabilities)

        device.last_seen = utcnow()
        db.commit()

    await websocket.accept()

    # Register in in-memory registry (this also broadcasts online devices to the user)
    online_device = await registry.register(
        device_id=device_id,
        user_id=user_id,
        name=device_name,
        platform=device_platform,
        capabilities=capabilities,
        websocket=websocket
    )

    logger.info(f"Device connected: {device_name} ({device_id}) platform={device_platform}")

    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue

            msg_type = data.get("type")

            if msg_type == "heartbeat":
                await registry.update_heartbeat(device_id)

            elif msg_type == "command":
                try:
                    cmd = WSCommandMessage(**data)
                    await registry.update_heartbeat(device_id)
                    # Handle command in a background task so incoming results/heartbeats aren't blocked
                    asyncio_task = asyncio.create_task(
                        command_router.handle_command(online_device, cmd)
                    )
                except Exception as e:
                    logger.warning(f"Malformed command from {device_id}: {e}")

            elif msg_type == "result":
                try:
                    result = WSResultMessage(**data)
                    await registry.update_heartbeat(device_id)
                    await command_router.handle_result(result)
                except Exception as e:
                    logger.warning(f"Malformed result from {device_id}: {e}")

            else:
                logger.debug(f"Unknown message type '{msg_type}' from {device_id}")

    except WebSocketDisconnect:
        logger.info(f"Device disconnected: {device_id}")
    except Exception as e:
        logger.info(f"WebSocket connection ended for {device_id}: {e}")
    finally:
        await registry.unregister(device_id)
        try:
            with SessionLocal() as db:
                db_device = db.get(Device, device_id)
                if db_device:
                    db_device.last_seen = utcnow()
                    db.commit()
        except Exception:
            pass
