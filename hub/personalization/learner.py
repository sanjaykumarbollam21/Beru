import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from hub.db import SessionLocal, CommandCorrection, SkillSequenceLog, utcnow
from hub.personalization.store import preference_store

logger = logging.getLogger(__name__)

class PersonalizationLearner:
    """
    Learns explicit user patterns from repeated corrections and sequences.
    Never silently changes behavior; generates suggestions requiring user confirmation.
    """

    def is_learning_enabled(self, user_id: str) -> bool:
        return bool(preference_store.get_preference(user_id, "learning_enabled", True))

    def record_correction(
        self,
        user_id: str,
        skill: str,
        intended_target: Optional[str],
        corrected_target: str
    ) -> Optional[str]:
        """
        Record a target device correction.
        If the same correction occurred 3 times for this skill and is not suppressed,
        returns a suggestion prompt string for Beru to ask the user.
        """
        if not self.is_learning_enabled(user_id):
            return None

        now = utcnow()
        with SessionLocal() as db:
            # Check if active suppression exists for this skill & target
            suppressed = db.query(CommandCorrection).filter(
                CommandCorrection.user_id == user_id,
                CommandCorrection.skill == skill,
                CommandCorrection.corrected_target == corrected_target,
                CommandCorrection.suppressed_until > now
            ).first()

            if suppressed:
                logger.info(f"Correction suggestion for {skill}->{corrected_target} currently suppressed until {suppressed.suppressed_until}")
                return None

            # Add new correction record
            entry = CommandCorrection(
                user_id=user_id,
                skill=skill,
                intended_target=intended_target,
                corrected_target=corrected_target,
                timestamp=now
            )
            db.add(entry)
            db.commit()

            # Count unsuppressed occurrences of this specific correction in last 30 days
            cutoff = now - timedelta(days=30)
            count = db.query(CommandCorrection).filter(
                CommandCorrection.user_id == user_id,
                CommandCorrection.skill == skill,
                CommandCorrection.corrected_target == corrected_target,
                CommandCorrection.timestamp >= cutoff
            ).count()

            # On the 3rd repetition, propose suggestion once!
            if count == 3:
                target_display = "phone" if "android" in corrected_target.lower() else "PC"
                suggestion = f"Should I always do that on your {target_display}?"
                logger.info(f"Generated target preference suggestion for user {user_id}: {suggestion}")
                return suggestion

        return None

    def accept_correction_suggestion(self, user_id: str, skill: str, corrected_target: str) -> None:
        """
        User accepted suggestion ("yes"): save as a learned preference.
        """
        defaults = preference_store.get_preference(user_id, "default_targets", {})
        if not isinstance(defaults, dict):
            defaults = {}
        defaults[skill] = corrected_target
        preference_store.set_preference(user_id, "default_targets", defaults, source="learned")
        logger.info(f"Learned target preference accepted: {skill} -> {corrected_target} for user {user_id}")

    def decline_correction_suggestion(self, user_id: str, skill: str, corrected_target: str) -> None:
        """
        User declined suggestion ("no"): suppress for 30 days.
        """
        suppress_date = utcnow() + timedelta(days=30)
        with SessionLocal() as db:
            records = db.query(CommandCorrection).filter(
                CommandCorrection.user_id == user_id,
                CommandCorrection.skill == skill,
                CommandCorrection.corrected_target == corrected_target
            ).all()
            for r in records:
                r.suppressed_until = suppress_date
            db.commit()
        logger.info(f"Suppressed suggestion for {skill} -> {corrected_target} for 30 days for user {user_id}")

    def record_skill_sequence(self, user_id: str, sequence: List[str], date_str: Optional[str] = None) -> Optional[str]:
        """
        Record sequence of 2+ skills executed within 5 minutes.
        If the exact sequence occurred on 3 separate days, return a routine suggestion once.
        """
        if not self.is_learning_enabled(user_id):
            return None

        if len(sequence) < 2:
            return None

        today = date_str or utcnow().strftime("%Y-%m-%d")
        seq_hash = hashlib.sha256(json.dumps(sequence).encode()).hexdigest()

        with SessionLocal() as db:
            # Check if this sequence already logged for today
            existing_today = db.query(SkillSequenceLog).filter(
                SkillSequenceLog.user_id == user_id,
                SkillSequenceLog.sequence_hash == seq_hash,
                SkillSequenceLog.date_str == today
            ).first()

            if not existing_today:
                log_entry = SkillSequenceLog(
                    user_id=user_id,
                    sequence_hash=seq_hash,
                    sequence_json=sequence,
                    date_str=today,
                    timestamp=utcnow()
                )
                db.add(log_entry)
                db.commit()

            # Check number of distinct days this sequence has been logged
            distinct_days = db.query(SkillSequenceLog.date_str).filter(
                SkillSequenceLog.user_id == user_id,
                SkillSequenceLog.sequence_hash == seq_hash
            ).distinct().count()

            if distinct_days == 3:
                # Offer routine suggestion once
                routine_name = f"{sequence[0].split('_')[0]}_{sequence[1].split('_')[0]}"
                suggestion = f"You often run {' then '.join(sequence)}. Would you like to save this as a routine called '{routine_name}'?"
                logger.info(f"Generated routine suggestion: {suggestion}")
                return suggestion

        return None

learner = PersonalizationLearner()
