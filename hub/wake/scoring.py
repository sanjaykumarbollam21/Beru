import logging
from typing import Dict, Optional, Tuple, Any
from hub.config import settings
from hub.wake.models import WakeClaim

logger = logging.getLogger(__name__)

class WakeScorer:
    def __init__(self):
        pass

    def calculate_score(
        self,
        claim: WakeClaim,
        is_active_device: bool = False,
        is_recent_winner: bool = False,
        is_preferred_device: bool = False,
        is_disabled: bool = False
    ) -> float:
        """
        Calculate weighted score for a wake claim.
        Returns 0.0 if disabled or under minimum threshold.
        """
        if is_disabled:
            return 0.0

        if claim.detector_score < settings.ARBITRATION_MIN_DETECTOR_SCORE:
            logger.info(f"Claim {claim.claim_id} rejected: detector score {claim.detector_score:.2f} < {settings.ARBITRATION_MIN_DETECTOR_SCORE}")
            return 0.0

        # Base components
        detector_component = claim.detector_score * settings.SCORE_WEIGHT_DETECTOR
        signal_component = claim.signal_level * settings.SCORE_WEIGHT_SIGNAL

        # Context components (up to 0.25 total)
        context_score = 0.0
        if is_active_device:
            context_score += 0.12
        if claim.screen_on or claim.in_use:
            context_score += 0.08
        if claim.charging:
            context_score += 0.05
        
        context_component = min(context_score, settings.SCORE_WEIGHT_CONTEXT)

        total_score = detector_component + signal_component + context_component

        # Hysteresis bonus for winner within last 10 seconds
        if is_recent_winner:
            total_score += 0.10

        # Manual override: preferred device bonus
        if is_preferred_device:
            total_score += 10.0

        return round(total_score, 4)

    def select_winner(
        self,
        claims: list[WakeClaim],
        device_platforms: Dict[str, str],
        active_device_id: Optional[str] = None,
        last_winner_device_id: Optional[str] = None,
        preferred_device_id: Optional[str] = None,
        disabled_device_ids: Optional[list[str]] = None
    ) -> Tuple[Optional[WakeClaim], Optional[WakeClaim], Dict[str, float]]:
        """
        Score all claims and select (winner, runner_up, score_map).
        Applies tie-breaking rules:
          1. Higher score
          2. Higher signal level
          3. Phone platform preference
        """
        disabled_set = set(disabled_device_ids or [])
        scores: Dict[str, float] = {}
        valid_candidates: list[Tuple[WakeClaim, float]] = []

        for claim in claims:
            score = self.calculate_score(
                claim=claim,
                is_active_device=(claim.device_id == active_device_id),
                is_recent_winner=(claim.device_id == last_winner_device_id),
                is_preferred_device=(claim.device_id == preferred_device_id),
                is_disabled=(claim.device_id in disabled_set)
            )
            scores[claim.device_id] = score
            if score >= settings.ARBITRATION_MIN_SCORE:
                valid_candidates.append((claim, score))

        if not valid_candidates:
            return None, None, scores

        # Sort with tie-breaking:
        # 1. Score (descending)
        # 2. Signal level (descending)
        # 3. Platform is phone / android (descending boolean)
        def sort_key(item: Tuple[WakeClaim, float]):
            c, s = item
            plat = device_platforms.get(c.device_id, "").lower()
            is_phone = 1 if ("android" in plat or "phone" in plat or "mobile" in plat) else 0
            return (s, c.signal_level, is_phone)

        valid_candidates.sort(key=sort_key, reverse=True)

        winner = valid_candidates[0][0]
        runner_up = valid_candidates[1][0] if len(valid_candidates) > 1 else None

        return winner, runner_up, scores

wake_scorer = WakeScorer()
