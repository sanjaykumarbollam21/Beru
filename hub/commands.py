import logging
from fastapi import APIRouter, Depends, HTTPException, status
from hub.auth import get_current_device
from hub.db import Device
from hub.dialog import dialog_manager
from hub.confirm import confirmation_gate
from hub.router import command_router
from hub.schemas import (
    TextCommandRequest,
    TextCommandResponse,
    ConfirmRequestPayload,
    CancelRequestPayload
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/command", tags=["commands"])

@router.post("/text", response_model=TextCommandResponse)
async def process_text_command(
    payload: TextCommandRequest,
    current_device: Device = Depends(get_current_device)
):
    turn_result = await dialog_manager.process_user_text(
        user_id=current_device.user_id,
        text=payload.text,
        sender_platform=current_device.platform,
        sender_device_id=current_device.id
    )

    if turn_result.type == "unknown":
        return TextCommandResponse(
            status="unknown",
            error=turn_result.message or "Unknown command"
        )

    if turn_result.type == "error":
        intent_dict = None
        if turn_result.intent:
            intent_dict = {
                "skill": turn_result.intent.skill.name,
                "target": turn_result.intent.target_device,
                "params": turn_result.intent.params
            }
        return TextCommandResponse(
            status="failed",
            intent=intent_dict,
            error=turn_result.error
        )

    if turn_result.type == "clarify":
        intent_dict = {
            "skill": turn_result.intent.skill.name,
            "target": turn_result.intent.target_device,
            "params": turn_result.intent.params
        }
        return TextCommandResponse(
            status="clarify",
            intent=intent_dict,
            question=turn_result.question,
            missing_slots=turn_result.missing_slots
        )

    if turn_result.type == "ready":
        intent = turn_result.intent
        intent_dict = {
            "skill": intent.skill.name,
            "target": intent.target_device,
            "params": intent.params
        }

        # Check if first step requires confirmation
        if intent.requires_confirmation:
            conf = confirmation_gate.create_confirmation(
                user_id=current_device.user_id,
                sender_device_id=current_device.id,
                intent=intent,
                remaining_plan=turn_result.plan[1:]
            )
            return TextCommandResponse(
                status="confirm_required",
                intent=intent_dict,
                confirmation_id=conf.id,
                prompt=conf.prompt
            )

        # No confirmation required, execute immediately
        plan = turn_result.plan or [intent]
        exec_res = await command_router.execute_plan(
            user_id=current_device.user_id,
            sender_device_id=current_device.id,
            plan=plan
        )

        if exec_res.get("status") == "ok":
            return TextCommandResponse(
                status="executed",
                intent=intent_dict,
                result=exec_res
            )
        else:
            return TextCommandResponse(
                status="failed",
                intent=intent_dict,
                result=exec_res,
                error=exec_res.get("error")
            )

    return TextCommandResponse(
        status="failed",
        error="Unhandled dialog state"
    )

@router.post("/confirm", response_model=TextCommandResponse)
async def confirm_command(
    payload: ConfirmRequestPayload,
    current_device: Device = Depends(get_current_device)
):
    ok, record, msg = confirmation_gate.confirm(
        confirmation_id=payload.confirmation_id,
        user_id=current_device.user_id
    )
    if not ok or not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )

    intent_dict = {
        "skill": record.intent.skill.name,
        "target": record.intent.target_device,
        "params": record.intent.params
    }

    # Execute the confirmed intent and any remaining plan
    plan = [record.intent] + record.remaining_plan
    exec_res = await command_router.execute_plan(
        user_id=current_device.user_id,
        sender_device_id=current_device.id,
        plan=plan
    )

    if exec_res.get("status") == "ok":
        return TextCommandResponse(
            status="executed",
            intent=intent_dict,
            result=exec_res
        )
    else:
        return TextCommandResponse(
            status="failed",
            intent=intent_dict,
            result=exec_res,
            error=exec_res.get("error")
        )

@router.post("/cancel")
async def cancel_command(
    payload: CancelRequestPayload,
    current_device: Device = Depends(get_current_device)
):
    ok, record, msg = confirmation_gate.cancel(
        confirmation_id=payload.confirmation_id,
        user_id=current_device.user_id
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {"status": "cancelled", "confirmation_id": payload.confirmation_id}
