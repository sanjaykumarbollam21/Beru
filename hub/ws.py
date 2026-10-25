import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.orm import Session
from hub.db import SessionLocal, utcnow, Device
from hub.auth import get_device_by_token
from hub.registry import registry
from hub.router import command_router
from hub.dialog import dialog_manager
from hub.confirm import confirmation_gate
from hub.clipboard.sync import clipboard_sync_manager
from hub.transfer.store import transfer_store
from hub.handover.manager import handover_manager
from hub.wake.models import WakeClaim
from hub.wake.arbiter import wake_arbiter
from hub.schemas import WSCommandMessage, WSResultMessage

logger = logging.getLogger(__name__)

import json
from hub.config import settings
from hub.security.tickets import ticket_manager
from hub.security.ratelimit import rate_limiter
from hub.reliability.idempotency import idempotency_store
from hub.reliability.health import metrics_collector

router = APIRouter(tags=["websocket"])

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    protocol_version: Optional[str] = Query(None)
):
    # Check protocol version
    if protocol_version and protocol_version not in settings.SUPPORTED_PROTOCOL_VERSIONS:
        await websocket.close(
            code=status.WS_1002_PROTOCOL_ERROR,
            reason="Protocol version not supported. Please update your Beru app."
        )
        return

    # Check authentication (tickets required; raw tokens in URL prohibited)
    device = None
    with SessionLocal() as db:
        if ticket:
            rec = ticket_manager.consume_ticket(ticket)
            if not rec:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired ticket")
                return
            device = db.query(Device).filter(Device.id == rec.device_id).first()
            if not device or device.is_revoked:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Device revoked")
                return
        elif token:
            if not settings.ALLOW_LEGACY_WS_TOKEN:
                logger.warning("Rejected WebSocket connection: raw tokens in URL query are prohibited.")
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Raw tokens in URL query are prohibited. Obtain a ticket via POST /auth/ticket."
                )
                return
            device = get_device_by_token(db, token)
            if not device or device.is_revoked:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
                return
        else:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication ticket")
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

    # Check pending ready transfers for this newly connected device
    pending_transfers = transfer_store.list_pending_for_device(user_id, device_id)
    for p_trf in pending_transfers:
        try:
            await websocket.send_json({
                "type": "file_ready",
                "transfer_id": p_trf.transfer_id,
                "name": p_trf.file_name,
                "size": p_trf.file_size,
                "sha256": p_trf.sha256,
                "mime": p_trf.mime,
                "from_device": p_trf.from_device_id
            })
        except Exception:
            pass

    try:
        while True:
            raw_text = await websocket.receive_text()
            if len(raw_text) > settings.MAX_WS_MESSAGE_SIZE_BYTES:
                logger.warning(f"Oversized message ({len(raw_text)} bytes) from {device_id}")
                await websocket.send_json({"type": "error", "message": "Message exceeds maximum allowed size"})
                continue

            try:
                data = json.loads(raw_text)
            except Exception:
                logger.warning(f"Malformed JSON from {device_id}")
                await websocket.send_json({"type": "error", "message": "Malformed message"})
                continue

            if not isinstance(data, dict):
                continue

            # Rate limit check per device
            allowed, _, _ = rate_limiter.check(f"ws_dev_{device_id}", max_requests=settings.RATE_LIMIT_PER_MINUTE_DEVICE, window_seconds=60.0)
            if not allowed:
                await websocket.send_json({"type": "error", "message": "Rate limit exceeded"})
                continue

            handover_manager.set_active_device(user_id, device_id)

            msg_type = data.get("type")

            if msg_type == "heartbeat":
                await registry.update_heartbeat(device_id)

            elif msg_type == "command":
                try:
                    cmd = WSCommandMessage(**data)
                    await registry.update_heartbeat(device_id)

                    is_dup, prev_res = idempotency_store.check_or_set(cmd.id)
                    if is_dup:
                        logger.info(f"Duplicate command ID {cmd.id} ignored")
                        if prev_res:
                            await websocket.send_json(prev_res)
                        continue

                    # Handle command in a background task so incoming results/heartbeats aren't blocked
                    asyncio_task = asyncio.create_task(
                        command_router.handle_command(online_device, cmd)
                    )
                except Exception as e:
                    logger.warning(f"Malformed command from {device_id}: {e}")
                    await websocket.send_json({"type": "error", "message": "Malformed command"})

            elif msg_type == "result":
                try:
                    result = WSResultMessage(**data)
                    await registry.update_heartbeat(device_id)
                    await command_router.handle_result(result)
                except Exception as e:
                    logger.warning(f"Malformed result from {device_id}: {e}")

            elif msg_type == "text_command":
                text = data.get("text", "")
                await registry.update_heartbeat(device_id)

                async def _run_text_command():
                    turn_result = await dialog_manager.process_user_text(
                        user_id=user_id,
                        text=text,
                        sender_platform=device_platform,
                        sender_device_id=device_id
                    )
                    if turn_result.type == "clarify":
                        await websocket.send_json({
                            "type": "clarify",
                            "question": turn_result.question,
                            "missing_slots": turn_result.missing_slots
                        })
                    elif turn_result.type == "ready":
                        intent = turn_result.intent
                        if intent.requires_confirmation:
                            conf = confirmation_gate.create_confirmation(
                                user_id=user_id,
                                sender_device_id=device_id,
                                intent=intent,
                                remaining_plan=turn_result.plan[1:]
                            )
                            await websocket.send_json({
                                "type": "confirm_request",
                                "confirmation_id": conf.id,
                                "skill": intent.skill.name,
                                "target": intent.target_device,
                                "params": intent.params,
                                "prompt": conf.prompt
                            })
                        else:
                            exec_res = await command_router.execute_plan(
                                user_id=user_id,
                                sender_device_id=device_id,
                                plan=turn_result.plan or [intent]
                            )
                            await websocket.send_json({
                                "type": "command_status",
                                "status": exec_res.get("status"),
                                "data": exec_res
                            })
                    elif turn_result.type == "error":
                        await websocket.send_json({
                            "type": "command_status",
                            "status": "error",
                            "error": turn_result.error
                        })
                    elif turn_result.type == "unknown":
                        await websocket.send_json({
                            "type": "command_status",
                            "status": "error",
                            "error": turn_result.message
                        })

                asyncio.create_task(_run_text_command())

            elif msg_type == "confirm":
                conf_id = data.get("confirmation_id")
                await registry.update_heartbeat(device_id)

                async def _run_confirm():
                    ok, record, msg = confirmation_gate.confirm(conf_id, user_id)
                    if ok and record:
                        plan = [record.intent] + record.remaining_plan
                        exec_res = await command_router.execute_plan(
                            user_id=user_id,
                            sender_device_id=device_id,
                            plan=plan
                        )
                        await websocket.send_json({
                            "type": "command_status",
                            "status": exec_res.get("status"),
                            "data": exec_res
                        })
                    else:
                        await websocket.send_json({
                            "type": "command_status",
                            "status": "error",
                            "error": msg
                        })

                asyncio.create_task(_run_confirm())

            elif msg_type == "cancel":
                conf_id = data.get("confirmation_id")
                await registry.update_heartbeat(device_id)

                async def _run_cancel():
                    ok, record, msg = confirmation_gate.cancel(conf_id, user_id)
                    await websocket.send_json({
                        "type": "command_status",
                        "status": "cancelled" if ok else "error",
                        "error": None if ok else msg
                    })

            elif msg_type == "clipboard_update":
                await registry.update_heartbeat(device_id)
                text = data.get("text", "")
                c_hash = data.get("hash")
                origin = data.get("origin_device", device_id)
                ok, err, push_msg = clipboard_sync_manager.update_clipboard(user_id, origin, text, c_hash)
                if ok and push_msg:
                    await clipboard_sync_manager.fan_out_clipboard(user_id, origin, push_msg)

            elif msg_type == "file_ack":
                await registry.update_heartbeat(device_id)
                t_id = data.get("transfer_id")
                if t_id:
                    rec = transfer_store.get_record(t_id)
                    if rec and rec.user_id == user_id:
                        rec.status = "delivered"
                        transfer_store.delete_transfer_data(t_id)

            elif msg_type == "handover_accept":
                await registry.update_heartbeat(device_id)
                ho_id = data.get("handover_id")
                if ho_id:
                    await handover_manager.accept_handover(ho_id, user_id, device_id)

            elif msg_type == "wake_claim":
                await registry.update_heartbeat(device_id)
                import uuid
                claim = WakeClaim(
                    claim_id=data.get("claim_id", str(uuid.uuid4())),
                    device_id=device_id,
                    user_id=user_id,
                    detector_score=float(data.get("detector_score", 0.0)),
                    signal_level=float(data.get("signal_level", 0.0)),
                    screen_on=bool(data.get("screen_on", False)),
                    in_use=bool(data.get("in_use", False)),
                    charging=bool(data.get("charging", False))
                )
                asyncio.create_task(wake_arbiter.submit_claim(claim))

            elif msg_type == "wake_failed":
                await registry.update_heartbeat(device_id)
                claim_id = data.get("claim_id", "")
                asyncio.create_task(wake_arbiter.handle_wake_failed(user_id=user_id, device_id=device_id, claim_id=claim_id))

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
