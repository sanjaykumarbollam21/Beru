import asyncio
import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple, Set
from hub.config import settings
from hub.wake.models import WakeClaim, WakeDecision
from hub.wake.scoring import wake_scorer
from hub.registry import registry
from hub.handover.manager import handover_manager

logger = logging.getLogger(__name__)

class WakeArbiter:
    def __init__(self):
        # user_id -> List[WakeClaim] collected during current window
        self._pending_claims: Dict[str, List[WakeClaim]] = {}
        # user_id -> asyncio.Task running the window
        self._window_tasks: Dict[str, asyncio.Task] = {}
        # user_id -> last_decision_timestamp
        self._cooldown_timestamps: Dict[str, float] = {}
        # user_id -> (last_winner_device_id, timestamp)
        self._recent_winners: Dict[str, Tuple[str, float]] = {}
        # user_id -> latest WakeDecision
        self._recent_decisions: Dict[str, WakeDecision] = {}

    def is_in_cooldown(self, user_id: str) -> bool:
        last = self._cooldown_timestamps.get(user_id, 0.0)
        return (time.time() - last) < settings.ARBITRATION_COOLDOWN_SECONDS

    def get_recent_winner(self, user_id: str) -> Optional[str]:
        if user_id in self._recent_winners:
            dev_id, ts = self._recent_winners[user_id]
            if (time.time() - ts) <= settings.ARBITRATION_HYSTERESIS_SECONDS:
                return dev_id
        return None

    async def submit_claim(self, claim: WakeClaim) -> None:
        user_id = claim.user_id

        if self.is_in_cooldown(user_id):
            await self._notify_device(claim.device_id, {"type": "wake_lose", "claim_id": claim.claim_id})
            return

        if user_id not in self._pending_claims:
            self._pending_claims[user_id] = []
        self._pending_claims[user_id].append(claim)

        if user_id not in self._window_tasks:
            window_task = asyncio.create_task(self._run_arbitration_window(user_id))
            self._window_tasks[user_id] = window_task

    async def _run_arbitration_window(self, user_id: str) -> None:
        try:
            delay = settings.ARBITRATION_WINDOW_MS / 1000.0
            await asyncio.sleep(delay)
            await self._resolve_claims(user_id)
        except Exception as e:
            logger.exception(f"Error during wake arbitration for user {user_id}: {e}")
        finally:
            self._window_tasks.pop(user_id, None)

    async def _resolve_claims(self, user_id: str) -> Optional[WakeDecision]:
        claims = self._pending_claims.pop(user_id, [])
        if not claims:
            return None

        # Get user preferences from personalization store
        preferred_device_id = None
        disabled_device_ids = []
        try:
            from hub.personalization.store import preference_store
            prefs = preference_store.get_all_preferences(user_id)
            preferred_device_id = prefs.get("preferred_wake_device")
            disabled_device_ids = prefs.get("wake_disabled_devices", [])
        except Exception as e:
            logger.debug(f"Could not load preferences in arbiter: {e}")

        # Active device from handover manager
        active_device_id = handover_manager.get_active_device(user_id)
        last_winner_device_id = self.get_recent_winner(user_id)

        # Gather device platforms
        device_platforms: Dict[str, str] = {}
        for claim in claims:
            online_dev = await registry.get_device(claim.device_id)
            if online_dev:
                device_platforms[claim.device_id] = online_dev.platform

        winner_claim, runner_up_claim, scores = wake_scorer.select_winner(
            claims=claims,
            device_platforms=device_platforms,
            active_device_id=active_device_id,
            last_winner_device_id=last_winner_device_id,
            preferred_device_id=preferred_device_id,
            disabled_device_ids=disabled_device_ids
        )

        decision = WakeDecision(
            user_id=user_id,
            winner_claim=winner_claim,
            winner_device_id=winner_claim.device_id if winner_claim else None,
            runner_up_claim=runner_up_claim,
            all_claims=claims,
            scores=scores,
            reason="preferred_override" if (winner_claim and winner_claim.device_id == preferred_device_id) else "scored"
        )

        self._recent_decisions[user_id] = decision
        self._cooldown_timestamps[user_id] = time.time()

        if winner_claim:
            self._recent_winners[user_id] = (winner_claim.device_id, time.time())
            logger.info(f"Wake decision for user {user_id}: WINNER={winner_claim.device_id} (score={scores.get(winner_claim.device_id, 0.0):.2f}) out of {len(claims)} claims")
        else:
            logger.info(f"Wake decision for user {user_id}: NO WINNER (all {len(claims)} claims below threshold)")

        # Dispatch wake_win and wake_lose
        for claim in claims:
            if winner_claim and claim.device_id == winner_claim.device_id:
                await self._notify_device(claim.device_id, {
                    "type": "wake_win",
                    "claim_id": claim.claim_id
                })
            else:
                await self._notify_device(claim.device_id, {
                    "type": "wake_lose",
                    "claim_id": claim.claim_id
                })

        return decision

    async def handle_wake_failed(self, user_id: str, device_id: str, claim_id: str) -> bool:
        """
        Handle a failed wake session from the winner. Promotes the runner-up once.
        """
        decision = self._recent_decisions.get(user_id)
        if not decision or not decision.runner_up_claim:
            return False

        if decision.winner_device_id != device_id:
            return False

        runner_up = decision.runner_up_claim
        logger.info(f"Promoting runner-up {runner_up.device_id} after {device_id} failed wake_claim {claim_id}")

        # Promote runner-up
        decision.winner_claim = runner_up
        decision.winner_device_id = runner_up.device_id
        decision.runner_up_claim = None
        self._recent_winners[user_id] = (runner_up.device_id, time.time())

        await self._notify_device(runner_up.device_id, {
            "type": "wake_win",
            "claim_id": runner_up.claim_id
        })
        return True

    async def _notify_device(self, device_id: str, message: dict) -> None:
        online_device = await registry.get_device(device_id)
        if online_device and online_device.websocket:
            try:
                await online_device.websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send {message.get('type')} to {device_id}: {e}")

wake_arbiter = WakeArbiter()
