import logging
from typing import Dict, List, Optional, Any
from hub.db import SessionLocal, UserPreference, UserFact, UserRoutine, utcnow

logger = logging.getLogger(__name__)

class PreferenceStore:
    """
    Persistent store for user preferences, remembered facts, and routines.
    Isolated strictly per user_id.
    """

    def get_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        with SessionLocal() as db:
            record = db.query(UserPreference).filter(
                UserPreference.user_id == user_id,
                UserPreference.key == key
            ).first()
            if record:
                return record.value
            return default

    def set_preference(self, user_id: str, key: str, value: Any, source: str = "user") -> None:
        with SessionLocal() as db:
            record = db.query(UserPreference).filter(
                UserPreference.user_id == user_id,
                UserPreference.key == key
            ).first()
            if record:
                record.value = value
                record.source = source
                record.updated_at = utcnow()
            else:
                record = UserPreference(
                    user_id=user_id,
                    key=key,
                    value=value,
                    source=source
                )
                db.add(record)
            db.commit()
            logger.info(f"Saved preference key='{key}' (source={source}) for user={user_id}")

    def delete_preference(self, user_id: str, key: str) -> bool:
        with SessionLocal() as db:
            record = db.query(UserPreference).filter(
                UserPreference.user_id == user_id,
                UserPreference.key == key
            ).first()
            if record:
                db.delete(record)
                db.commit()
                return True
            return False

    def get_all_preferences(self, user_id: str) -> Dict[str, Any]:
        with SessionLocal() as db:
            records = db.query(UserPreference).filter(UserPreference.user_id == user_id).all()
            return {r.key: r.value for r in records}

    def get_all_preference_records(self, user_id: str) -> List[Dict[str, Any]]:
        with SessionLocal() as db:
            records = db.query(UserPreference).filter(UserPreference.user_id == user_id).all()
            return [{
                "key": r.key,
                "value": r.value,
                "source": r.source,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None
            } for r in records]

    # Specialized helpers for Phase 2 Resolver integration
    def get_default_target_for_skill(self, user_id: str, skill_name: str) -> Optional[str]:
        defaults = self.get_preference(user_id, "default_targets", {})
        if isinstance(defaults, dict):
            return defaults.get(skill_name)
        return None

    def get_preferred_app(self, user_id: str, category_or_alias: str) -> Optional[str]:
        apps = self.get_preference(user_id, "preferred_apps", {})
        if isinstance(apps, dict):
            return apps.get(category_or_alias.lower())
        return None

    def get_contact_nickname(self, user_id: str, nickname: str) -> Optional[str]:
        contacts = self.get_preference(user_id, "contacts", {})
        if isinstance(contacts, dict):
            return contacts.get(nickname.lower())
        return None

    def get_device_alias(self, user_id: str, alias: str) -> Optional[str]:
        aliases = self.get_preference(user_id, "device_aliases", {})
        if isinstance(aliases, dict):
            return aliases.get(alias.lower())
        return None

    # Remembered Facts
    def add_fact(self, user_id: str, text: str) -> str:
        with SessionLocal() as db:
            fact = UserFact(user_id=user_id, text=text)
            db.add(fact)
            db.commit()
            db.refresh(fact)
            logger.info(f"Saved fact {fact.id} for user={user_id}")
            return fact.id

    def get_all_facts(self, user_id: str) -> List[Dict[str, Any]]:
        with SessionLocal() as db:
            facts = db.query(UserFact).filter(UserFact.user_id == user_id).order_by(UserFact.created_at.desc()).all()
            return [{"id": f.id, "text": f.text, "created_at": f.created_at.isoformat()} for f in facts]

    def search_facts(self, user_id: str, query: str) -> List[Dict[str, Any]]:
        query_words = set(query.lower().split())
        all_facts = self.get_all_facts(user_id)
        matches = []
        for f in all_facts:
            f_words = set(f["text"].lower().split())
            if query.lower() in f["text"].lower() or (query_words & f_words):
                matches.append(f)
        return matches

    def delete_fact(self, user_id: str, fact_id: str) -> bool:
        with SessionLocal() as db:
            fact = db.query(UserFact).filter(UserFact.user_id == user_id, UserFact.id == fact_id).first()
            if fact:
                db.delete(fact)
                db.commit()
                return True
            return False

    def delete_facts_by_query(self, user_id: str, query: str) -> int:
        matches = self.search_facts(user_id, query)
        count = 0
        with SessionLocal() as db:
            for m in matches:
                fact = db.query(UserFact).filter(UserFact.user_id == user_id, UserFact.id == m["id"]).first()
                if fact:
                    db.delete(fact)
                    count += 1
            db.commit()
        return count

    # Routines
    def create_routine(self, user_id: str, name: str, steps: list) -> str:
        clean_name = name.strip().lower()
        with SessionLocal() as db:
            routine = db.query(UserRoutine).filter(UserRoutine.user_id == user_id, UserRoutine.name == clean_name).first()
            if routine:
                routine.steps = steps
            else:
                routine = UserRoutine(user_id=user_id, name=clean_name, steps=steps)
                db.add(routine)
            db.commit()
            db.refresh(routine)
            logger.info(f"Created/updated routine '{clean_name}' for user={user_id}")
            return routine.id

    def get_routine(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        clean_name = name.strip().lower()
        with SessionLocal() as db:
            routine = db.query(UserRoutine).filter(UserRoutine.user_id == user_id, UserRoutine.name == clean_name).first()
            if routine:
                return {
                    "id": routine.id,
                    "name": routine.name,
                    "steps": routine.steps,
                    "created_at": routine.created_at.isoformat()
                }
            return None

    def list_routines(self, user_id: str) -> List[Dict[str, Any]]:
        with SessionLocal() as db:
            routines = db.query(UserRoutine).filter(UserRoutine.user_id == user_id).all()
            return [{
                "id": r.id,
                "name": r.name,
                "steps": r.steps,
                "created_at": r.created_at.isoformat()
            } for r in routines]

    def delete_routine(self, user_id: str, name: str) -> bool:
        clean_name = name.strip().lower()
        with SessionLocal() as db:
            routine = db.query(UserRoutine).filter(UserRoutine.user_id == user_id, UserRoutine.name == clean_name).first()
            if routine:
                db.delete(routine)
                db.commit()
                return True
            return False

    # Export & Reset
    def export_user_data(self, user_id: str) -> Dict[str, Any]:
        return {
            "preferences": self.get_all_preference_records(user_id),
            "facts": self.get_all_facts(user_id),
            "routines": self.list_routines(user_id)
        }

    def reset_user_data(self, user_id: str) -> None:
        with SessionLocal() as db:
            db.query(UserPreference).filter(UserPreference.user_id == user_id).delete()
            db.query(UserFact).filter(UserFact.user_id == user_id).delete()
            db.query(UserRoutine).filter(UserRoutine.user_id == user_id).delete()
            db.commit()
            logger.info(f"Reset all personalization data for user={user_id}")

preference_store = PreferenceStore()
