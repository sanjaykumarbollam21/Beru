import time
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from starlette.websockets import WebSocket, WebSocketState
from hub.config import settings

@dataclass
class OnlineDevice:
    device_id: str
    user_id: str
    name: str
    platform: str
    capabilities: List[str]
    websocket: WebSocket
    last_heartbeat: float

class DeviceRegistry:
    def __init__(self):
        # device_id -> OnlineDevice
        self._devices: Dict[str, OnlineDevice] = {}
        # user_id -> set of device_ids
        self._user_devices: Dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        device_id: str,
        user_id: str,
        name: str,
        platform: str,
        capabilities: List[str],
        websocket: WebSocket
    ) -> OnlineDevice:
        async with self._lock:
            # If device was already registered (e.g. reconnecting), clean up old connection
            if device_id in self._devices:
                old = self._devices[device_id]
                try:
                    if old.websocket.client_state == WebSocketState.CONNECTED:
                        await old.websocket.close()
                except Exception:
                    pass

            entry = OnlineDevice(
                device_id=device_id,
                user_id=user_id,
                name=name,
                platform=platform.lower(),
                capabilities=list(capabilities),
                websocket=websocket,
                last_heartbeat=time.time()
            )
            self._devices[device_id] = entry
            if user_id not in self._user_devices:
                self._user_devices[user_id] = set()
            self._user_devices[user_id].add(device_id)

        # Broadcast update to user's devices
        await self.broadcast_devices(user_id)
        return entry

    async def unregister(self, device_id: str) -> Optional[OnlineDevice]:
        entry = None
        user_id = None
        async with self._lock:
            if device_id in self._devices:
                entry = self._devices.pop(device_id)
                user_id = entry.user_id
                if user_id in self._user_devices:
                    self._user_devices[user_id].discard(device_id)
                    if not self._user_devices[user_id]:
                        del self._user_devices[user_id]

        if user_id:
            await self.broadcast_devices(user_id)
        return entry

    async def update_heartbeat(self, device_id: str):
        async with self._lock:
            if device_id in self._devices:
                self._devices[device_id].last_heartbeat = time.time()

    async def get_device(self, device_id: str) -> Optional[OnlineDevice]:
        async with self._lock:
            return self._devices.get(device_id)

    async def get_user_devices(self, user_id: str) -> List[OnlineDevice]:
        async with self._lock:
            device_ids = self._user_devices.get(user_id, set())
            return [self._devices[d_id] for d_id in device_ids if d_id in self._devices]

    async def resolve_target(
        self,
        user_id: str,
        sender_device_id: str,
        target: str
    ) -> Optional[OnlineDevice]:
        async with self._lock:
            target_norm = target.strip().lower()
            if target_norm == "self":
                return self._devices.get(sender_device_id)

            # Map common aliases to platform names
            platform_alias = {
                "pc": "windows",
                "laptop": "windows",
                "computer": "windows",
                "desktop": "windows",
                "phone": "android",
                "mobile": "android"
            }.get(target_norm, target_norm)

            # Check if target is a specific device_id
            if target in self._devices:
                dev = self._devices[target]
                if dev.user_id == user_id:
                    return dev

            # Check if target is a platform (e.g., "windows", "android")
            user_device_ids = self._user_devices.get(user_id, set())
            for d_id in user_device_ids:
                dev = self._devices.get(d_id)
                if dev and dev.platform == platform_alias:
                    return dev

            return None

    async def broadcast_devices(self, user_id: str):
        async with self._lock:
            device_ids = list(self._user_devices.get(user_id, set()))
            devices = [self._devices[d_id] for d_id in device_ids if d_id in self._devices]
            payload = {
                "type": "devices",
                "online": [
                    {
                        "id": d.device_id,
                        "name": d.name,
                        "platform": d.platform,
                        "capabilities": d.capabilities
                    }
                    for d in devices
                ]
            }
            recipients = list(devices)

        # Send outside lock to avoid deadlocks
        dead_devices = []
        for dev in recipients:
            try:
                await dev.websocket.send_json(payload)
            except Exception:
                dead_devices.append(dev.device_id)

        for d_id in dead_devices:
            await self.unregister(d_id)

    async def check_heartbeat_timeouts(self, timeout_seconds: float = settings.HEARTBEAT_TIMEOUT_SECONDS):
        now = time.time()
        timed_out = []
        async with self._lock:
            for dev_id, dev in list(self._devices.items()):
                if now - dev.last_heartbeat > timeout_seconds:
                    timed_out.append(dev)

        for dev in timed_out:
            try:
                if dev.websocket.client_state == WebSocketState.CONNECTED:
                    await dev.websocket.close(code=1000, reason="Heartbeat timeout")
            except Exception:
                pass
            await self.unregister(dev.device_id)

    async def disconnect_device(self, device_id: str, code: int = 1008, reason: str = "Device disconnected"):
        async with self._lock:
            dev = self._devices.get(device_id)
        if dev:
            try:
                if dev.websocket.client_state == WebSocketState.CONNECTED:
                    await dev.websocket.close(code=code, reason=reason)
            except Exception:
                pass
            await self.unregister(device_id)

registry = DeviceRegistry()

