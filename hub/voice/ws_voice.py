import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from hub.db import SessionLocal, Device, utcnow
from hub.auth import get_device_by_token
from hub.config import settings
from hub.voice.session import (
    voice_session_manager,
    strip_wake_phrase,
    classify_spoken_confirmation
)
from hub.voice.stt import stt_orchestrator
from hub.voice.tts import tts_orchestrator
from hub.dialog import dialog_manager
from hub.confirm import confirmation_gate
from hub.router import command_router

logger = logging.getLogger(__name__)

from hub.security.tickets import ticket_manager

router = APIRouter(tags=["voice"])

@router.websocket("/voice")
async def voice_websocket_endpoint(
    websocket: WebSocket,
    ticket: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    protocol_version: Optional[str] = Query(None)
):
    if protocol_version and protocol_version not in settings.SUPPORTED_PROTOCOL_VERSIONS:
        await websocket.close(
            code=status.WS_1002_PROTOCOL_ERROR,
            reason="Protocol version not supported. Please update your Beru app."
        )
        return

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
            logger.warning("Rejected voice WebSocket connection: raw tokens in URL query are prohibited.")
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Raw tokens in URL query are prohibited. Obtain a ticket via POST /auth/ticket."
            )
            return
        else:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication ticket")
            return

        device_id = device.id
        user_id = device.user_id
        device_platform = device.platform
        device_name = device.name

    await websocket.accept()
    logger.info(f"Voice WebSocket connected for {device_name} ({device_id})")

    session = voice_session_manager.get_or_create(user_id=user_id, device_id=device_id)
    tts_mode = settings.DEFAULT_TTS_PROVIDER

    async def send_spoken_reply(
        reply_text: str,
        expect_reply: bool = False,
        action: str = "none"
    ):
        nonlocal tts_mode
        # Send reply JSON
        await websocket.send_json({
            "type": "reply",
            "text": reply_text,
            "speak": True,
            "tts": tts_mode,
            "expect_reply": expect_reply,
            "action": action
        })

        # If hub TTS requested, synthesize audio and stream chunks
        if tts_mode == "hub":
            try:
                audio_bytes = await tts_orchestrator.synthesize(reply_text)
                # Stream in 1024-byte chunks
                chunk_size = 1024
                for i in range(0, len(audio_bytes), chunk_size):
                    chunk = audio_bytes[i:i + chunk_size]
                    await websocket.send_bytes(chunk)
            except Exception as e:
                logger.error(f"TTS synthesis failed: {e}")

        if not expect_reply:
            await websocket.send_json({"type": "done"})

    async def handle_complete_utterance():
        nonlocal tts_mode
        await websocket.send_json({"type": "thinking"})
        audio_bytes = session.get_audio_bytes()

        if len(audio_bytes) < 100:
            await websocket.send_json({
                "type": "error",
                "code": "no_speech",
                "message": "No audio received"
            })
            return

        try:
            raw_transcript = await stt_orchestrator.transcribe_with_fallback(
                pcm_bytes=audio_bytes,
                sample_rate=settings.SAMPLE_RATE
            )
        except Exception as e:
            logger.error(f"STT failed: {e}")
            await websocket.send_json({
                "type": "error",
                "code": "stt_failed",
                "message": str(e)
            })
            return

        await websocket.send_json({
            "type": "final_transcript",
            "text": raw_transcript
        })

        text = strip_wake_phrase(raw_transcript)
        if not text:
            await websocket.send_json({"type": "done"})
            return

        # Check if session is expecting a spoken confirmation or clarification
        if session.waiting_for_confirmation and session.pending_confirmation_id:
            choice = classify_spoken_confirmation(text)
            if choice is True:
                ok, record, msg = confirmation_gate.confirm(session.pending_confirmation_id, user_id)
                if ok and record:
                    plan = [record.intent] + record.remaining_plan
                    exec_res = await command_router.execute_plan(
                        user_id=user_id,
                        sender_device_id=device_id,
                        plan=plan
                    )
                    reply_msg = f"Confirmed. {record.intent.skill.name} executed successfully."
                else:
                    reply_msg = f"Could not confirm: {msg}"
                session.clear_pending()
                await send_spoken_reply(reply_msg, expect_reply=False)
                return

            elif choice is False:
                confirmation_gate.cancel(session.pending_confirmation_id, user_id)
                session.clear_pending()
                await send_spoken_reply("Cancelled.", expect_reply=False)
                return

            else:
                # Unclear response
                session.reprompt_count += 1
                if session.reprompt_count == 1:
                    reprompt_msg = "I didn't catch that. Please say yes to confirm or no to cancel."
                    await send_spoken_reply(reprompt_msg, expect_reply=True, action="confirm")
                    session.start_listening()
                    await websocket.send_json({"type": "listening"})
                    return
                else:
                    confirmation_gate.cancel(session.pending_confirmation_id, user_id)
                    session.clear_pending()
                    await send_spoken_reply("Action cancelled due to unclear response.", expect_reply=False)
                    return

        # Route through Phase 2 dialog & intent pipeline
        turn_result = await dialog_manager.process_user_text(
            user_id=user_id,
            text=text,
            sender_platform=device_platform,
            sender_device_id=device_id
        )

        if turn_result.type == "clarify":
            session.set_pending_clarification()
            await send_spoken_reply(
                reply_text=turn_result.question,
                expect_reply=True,
                action="clarify"
            )
            session.start_listening()
            await websocket.send_json({"type": "listening"})
            return

        elif turn_result.type == "ready":
            intent = turn_result.intent
            if intent.requires_confirmation:
                conf = confirmation_gate.create_confirmation(
                    user_id=user_id,
                    sender_device_id=device_id,
                    intent=intent,
                    remaining_plan=turn_result.plan[1:]
                )
                session.set_pending_confirmation(conf.id)
                await send_spoken_reply(
                    reply_text=conf.prompt,
                    expect_reply=True,
                    action="confirm"
                )
                session.start_listening()
                await websocket.send_json({"type": "listening"})
                return
            else:
                exec_res = await command_router.execute_plan(
                    user_id=user_id,
                    sender_device_id=device_id,
                    plan=turn_result.plan or [intent]
                )
                if exec_res.get("status") == "ok":
                    reply_msg = f"Done. Executed {intent.skill.name} on {intent.target_device}."
                else:
                    reply_msg = f"Command failed: {exec_res.get('error', 'unknown error')}."
                await send_spoken_reply(reply_msg, expect_reply=False)
                return

        elif turn_result.type == "error":
            await send_spoken_reply(f"Error: {turn_result.error}", expect_reply=False)
            return

        else:
            await send_spoken_reply(
                f"Sorry, {settings.ASSISTANT_NAME} didn't understand that command.",
                expect_reply=False
            )
            return

    try:
        while True:
            message = await websocket.receive()
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                except Exception:
                    continue

                msg_type = data.get("type")

                if msg_type == "voice_start":
                    mode = data.get("mode", "wake_word")
                    tts_mode = data.get("tts", settings.DEFAULT_TTS_PROVIDER)
                    session.mode = mode
                    session.start_listening()
                    await websocket.send_json({"type": "listening"})

                elif msg_type == "voice_end":
                    if session.state == "listening":
                        await handle_complete_utterance()

                elif msg_type == "voice_cancel":
                    session.clear_pending()
                    session.state = "idle"
                    await websocket.send_json({"type": "done"})

            elif "bytes" in message:
                pcm_frame = message["bytes"]
                if session.state == "listening":
                    vad_status, _ = session.add_audio_frame(pcm_frame)

                    if vad_status == "no_speech":
                        await websocket.send_json({
                            "type": "error",
                            "code": "no_speech",
                            "message": "No speech detected"
                        })
                        session.state = "idle"

                    elif vad_status in ("endpoint_detected", "hard_cap"):
                        await handle_complete_utterance()

    except WebSocketDisconnect:
        logger.info(f"Voice WebSocket disconnected: {device_id}")
    except Exception as e:
        logger.info(f"Voice WebSocket connection closed for {device_id}: {e}")
    finally:
        voice_session_manager.remove(user_id, device_id)
