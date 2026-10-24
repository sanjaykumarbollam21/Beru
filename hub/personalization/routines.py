import logging
from typing import Dict, List, Optional, Any
from hub.personalization.store import preference_store
from hub.skills.base import skill_registry
from hub.router import command_router

logger = logging.getLogger(__name__)

class RoutineManager:
    """
    Manages named multi-step routines.
    Executes sequentially through the command router with per-step confirmation rules.
    """

    def create_routine(self, user_id: str, name: str, steps: List[Dict[str, Any]]) -> str:
        """
        Validate and save a routine.
        Steps format: [{"skill": "set_volume", "target": "pc", "params": {"level": 20}}, ...]
        """
        if not name or not steps:
            raise ValueError("Routine name and at least one step are required")

        # Validate that skills exist
        for s in steps:
            skill_name = s.get("skill")
            if not skill_registry.get(skill_name):
                raise ValueError(f"Unknown skill in routine step: {skill_name}")

        return preference_store.create_routine(user_id=user_id, name=name, steps=steps)

    def get_routine(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        return preference_store.get_routine(user_id=user_id, name=name)

    def list_routines(self, user_id: str) -> List[Dict[str, Any]]:
        return preference_store.list_routines(user_id=user_id)

    def delete_routine(self, user_id: str, name: str) -> bool:
        return preference_store.delete_routine(user_id=user_id, name=name)

    async def execute_routine(
        self,
        user_id: str,
        sender_device_id: str,
        name: str
    ) -> Dict[str, Any]:
        """
        Execute routine steps sequentially.
        Stops on first failure. Returns execution summary.
        """
        routine = self.get_routine(user_id, name)
        if not routine:
            return {"status": "error", "error": f"Routine '{name}' not found"}

        steps = routine.get("steps", [])
        executed_steps = []

        for idx, step_dict in enumerate(steps):
            skill_name = step_dict.get("skill")
            target = step_dict.get("target", "self")
            params = step_dict.get("params", {})

            skill = skill_registry.get(skill_name)
            if not skill:
                return {
                    "status": "error",
                    "error": f"Step #{idx+1} failed: skill '{skill_name}' not found",
                    "completed_steps": executed_steps
                }

            # Build resolved intent
            from hub.intent.resolver import ResolvedIntent
            intent = ResolvedIntent(
                skill=skill,
                target_platform=target,
                target_device=target,
                params=params,
                confidence=1.0,
                requires_confirmation=(skill.confirmation == "hard")
            )

            res = await command_router.execute_plan(
                user_id=user_id,
                sender_device_id=sender_device_id,
                plan=[intent]
            )

            if res.get("status") != "ok":
                logger.warning(f"Routine '{name}' stopped at step {idx+1} ({skill_name}): {res.get('error')}")
                return {
                    "status": "error",
                    "error": f"Routine '{name}' stopped at step {idx+1} ({skill_name}): {res.get('error')}",
                    "failed_step": idx + 1,
                    "completed_steps": executed_steps
                }

            executed_steps.append({"step": idx + 1, "skill": skill_name, "result": res})

        logger.info(f"Routine '{name}' completed successfully ({len(executed_steps)} steps)")
        return {
            "status": "ok",
            "routine": name,
            "steps_count": len(executed_steps),
            "completed_steps": executed_steps
        }

routine_manager = RoutineManager()
