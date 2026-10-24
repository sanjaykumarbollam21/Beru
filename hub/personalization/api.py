import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from hub.auth import get_current_device
from hub.db import Device
from hub.personalization.store import preference_store
from hub.personalization.routines import routine_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/personalization", tags=["personalization"])

@router.get("")
async def get_personalization_overview(
    current_device: Device = Depends(get_current_device)
) -> Dict[str, Any]:
    """Get all preferences, routines, and remembered facts for current user."""
    return preference_store.export_user_data(current_device.user_id)

@router.put("/preferences/{key}")
async def set_preference_endpoint(
    key: str,
    payload: Dict[str, Any] = Body(...),
    current_device: Device = Depends(get_current_device)
) -> Dict[str, Any]:
    """Set or update a specific preference key."""
    value = payload.get("value")
    source = payload.get("source", "user")
    preference_store.set_preference(current_device.user_id, key, value, source=source)
    return {"status": "ok", "key": key, "value": value, "source": source}

@router.delete("/preferences/{key}")
async def delete_preference_endpoint(
    key: str,
    current_device: Device = Depends(get_current_device)
) -> Dict[str, Any]:
    """Delete a specific preference key."""
    deleted = preference_store.delete_preference(current_device.user_id, key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Preference not found")
    return {"status": "ok", "deleted_key": key}

@router.post("/export")
async def export_personalization_data(
    current_device: Device = Depends(get_current_device)
) -> Dict[str, Any]:
    """Export all personalization data as JSON."""
    return preference_store.export_user_data(current_device.user_id)

@router.delete("")
async def reset_all_personalization(
    current_device: Device = Depends(get_current_device)
) -> Dict[str, Any]:
    """Reset and delete all personalization data for the user."""
    preference_store.reset_user_data(current_device.user_id)
    return {"status": "ok", "message": "All personalization data deleted"}

# Routines Endpoints
@router.get("/routines")
async def list_routines_endpoint(
    current_device: Device = Depends(get_current_device)
) -> List[Dict[str, Any]]:
    return routine_manager.list_routines(current_device.user_id)

@router.post("/routines")
async def create_routine_endpoint(
    payload: Dict[str, Any] = Body(...),
    current_device: Device = Depends(get_current_device)
) -> Dict[str, Any]:
    name = payload.get("name")
    steps = payload.get("steps", [])
    if not name or not steps:
        raise HTTPException(status_code=400, detail="Name and steps are required")
    try:
        routine_id = routine_manager.create_routine(current_device.user_id, name, steps)
        return {"status": "ok", "routine_id": routine_id, "name": name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/routines/{name}")
async def delete_routine_endpoint(
    name: str,
    current_device: Device = Depends(get_current_device)
) -> Dict[str, Any]:
    deleted = routine_manager.delete_routine(current_device.user_id, name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Routine not found")
    return {"status": "ok", "deleted_routine": name}

# Facts Endpoints
@router.get("/facts")
async def list_facts_endpoint(
    current_device: Device = Depends(get_current_device)
) -> List[Dict[str, Any]]:
    return preference_store.get_all_facts(current_device.user_id)

@router.post("/facts")
async def create_fact_endpoint(
    payload: Dict[str, Any] = Body(...),
    current_device: Device = Depends(get_current_device)
) -> Dict[str, Any]:
    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="Fact text is required")
    fact_id = preference_store.add_fact(current_device.user_id, text)
    return {"status": "ok", "fact_id": fact_id, "text": text}

@router.delete("/facts/{fact_id}")
async def delete_fact_endpoint(
    fact_id: str,
    current_device: Device = Depends(get_current_device)
) -> Dict[str, Any]:
    deleted = preference_store.delete_fact(current_device.user_id, fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "ok", "deleted_fact_id": fact_id}
