import asyncio
import uuid
import logging
from typing import Dict, Any, Optional
from hub.registry import registry, OnlineDevice
from hub.schemas import WSCommandMessage, WSResultMessage
from hub.config import settings

logger = logging.getLogger(__name__)

class CommandRouter:
    def __init__(self):
        # command_id -> asyncio.Future[WSResultMessage]
        self._pending_commands: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def handle_command(
        self,
        sender: OnlineDevice,
        command: WSCommandMessage,
        timeout: float = settings.COMMAND_TIMEOUT_SECONDS
    ):
        # 1. Resolve target
        target_device = await registry.resolve_target(
            user_id=sender.user_id,
            sender_device_id=sender.device_id,
            target=command.target
        )

        # 2. Check offline
        if not target_device:
            status_msg = {
                "type": "command_status",
                "command_id": command.id,
                "status": "offline"
            }
            try:
                await sender.websocket.send_json(status_msg)
            except Exception as e:
                logger.warning(f"Failed to send offline status to {sender.device_id}: {e}")
            return

        # 3. Check capabilities
        if command.action not in target_device.capabilities:
            status_msg = {
                "type": "command_status",
                "command_id": command.id,
                "status": "error",
                "error": "unsupported"
            }
            try:
                await sender.websocket.send_json(status_msg)
            except Exception as e:
                logger.warning(f"Failed to send unsupported error to {sender.device_id}: {e}")
            return

        # 4. Prepare future for awaiting result
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        async with self._lock:
            self._pending_commands[command.id] = fut

        # Send execute message to target
        execute_msg = {
            "type": "execute",
            "command_id": command.id,
            "action": command.action,
            "params": command.params,
            "from_device": sender.device_id
        }

        try:
            await target_device.websocket.send_json(execute_msg)
        except Exception as e:
            logger.warning(f"Failed to send execute to target {target_device.device_id}: {e}")
            async with self._lock:
                self._pending_commands.pop(command.id, None)
            try:
                await sender.websocket.send_json({
                    "type": "command_status",
                    "command_id": command.id,
                    "status": "offline"
                })
            except Exception:
                pass
            return

        # Notify sender that command was delivered to target
        delivered_msg = {
            "type": "command_status",
            "command_id": command.id,
            "status": "delivered"
        }
        try:
            await sender.websocket.send_json(delivered_msg)
        except Exception as e:
            logger.warning(f"Failed to send delivered status to {sender.device_id}: {e}")

        # 5. Await result with timeout
        try:
            result: WSResultMessage = await asyncio.wait_for(fut, timeout=timeout)
            response_msg = {
                "type": "command_status",
                "command_id": command.id,
                "status": result.status,
                "data": result.data
            }
            await sender.websocket.send_json(response_msg)
        except asyncio.TimeoutError:
            timeout_msg = {
                "type": "command_status",
                "command_id": command.id,
                "status": "error",
                "error": "timeout"
            }
            try:
                await sender.websocket.send_json(timeout_msg)
            except Exception as e:
                logger.warning(f"Failed to send timeout status to {sender.device_id}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error while awaiting command result: {e}")
            try:
                await sender.websocket.send_json({
                    "type": "command_status",
                    "command_id": command.id,
                    "status": "error",
                    "error": str(e)
                })
            except Exception:
                pass
        finally:
            async with self._lock:
                self._pending_commands.pop(command.id, None)

    async def handle_result(self, result: WSResultMessage):
        async with self._lock:
            fut = self._pending_commands.get(result.command_id)
            if fut and not fut.done():
                fut.set_result(result)

    async def execute_intent(
        self,
        user_id: str,
        sender_device_id: str,
        target: str,
        action: str,
        params: Dict[str, Any],
        command_id: Optional[str] = None,
        timeout: float = settings.COMMAND_TIMEOUT_SECONDS
    ) -> Dict[str, Any]:
        cmd_id = command_id or f"cmd-{uuid.uuid4().hex[:8]}"

        # 1. Resolve target
        target_device = await registry.resolve_target(
            user_id=user_id,
            sender_device_id=sender_device_id,
            target=target
        )

        if not target_device:
            return {
                "command_id": cmd_id,
                "status": "offline",
                "error": f"Target device '{target}' is offline"
            }

        if action not in target_device.capabilities:
            return {
                "command_id": cmd_id,
                "status": "error",
                "error": "unsupported"
            }

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        async with self._lock:
            self._pending_commands[cmd_id] = fut

        execute_msg = {
            "type": "execute",
            "command_id": cmd_id,
            "action": action,
            "params": params,
            "from_device": sender_device_id
        }

        try:
            await target_device.websocket.send_json(execute_msg)
        except Exception as e:
            logger.warning(f"Failed to send execute to target {target_device.device_id}: {e}")
            async with self._lock:
                self._pending_commands.pop(cmd_id, None)
            return {
                "command_id": cmd_id,
                "status": "offline",
                "error": "Target disconnected during delivery"
            }

        try:
            result: WSResultMessage = await asyncio.wait_for(fut, timeout=timeout)
            return {
                "command_id": cmd_id,
                "status": result.status,
                "data": result.data
            }
        except asyncio.TimeoutError:
            return {
                "command_id": cmd_id,
                "status": "error",
                "error": "timeout"
            }
        except Exception as e:
            return {
                "command_id": cmd_id,
                "status": "error",
                "error": str(e)
            }
        finally:
            async with self._lock:
                self._pending_commands.pop(cmd_id, None)

    async def execute_plan(
        self,
        user_id: str,
        sender_device_id: str,
        plan: list,
        start_step: int = 0
    ) -> Dict[str, Any]:
        results = []
        for i in range(start_step, len(plan)):
            intent = plan[i]
            res = await self.execute_intent(
                user_id=user_id,
                sender_device_id=sender_device_id,
                target=intent.target_device,
                action=intent.skill.get_action_name(),
                params=intent.params
            )
            results.append({
                "step": i + 1,
                "skill": intent.skill.name,
                "result": res
            })
            if res.get("status") != "ok":
                return {
                    "status": "failed",
                    "failed_step": i + 1,
                    "skill": intent.skill.name,
                    "error": res.get("error") or res.get("status"),
                    "completed_steps": results
                }
        return {
            "status": "ok",
            "completed_steps": results
        }

command_router = CommandRouter()

