import secrets
import time
import logging
from typing import Optional, Dict
from dataclasses import dataclass
from hub.config import settings
from hub.security.audit import audit_logger

logger = logging.getLogger(__name__)

@dataclass
class TicketRecord:
    ticket: str
    device_id: str
    user_id: str
    created_at: float
    expires_at: float
    consumed: bool = False

class TicketManager:
    """
    Manages short-lived, single-use WebSocket tickets.
    Replaces long-lived tokens in URLs to prevent leaking tokens into proxy/server logs.
    """
    def __init__(self, default_ttl_seconds: int = 30):
        self.default_ttl = default_ttl_seconds
        # ticket_str -> TicketRecord
        self._tickets: Dict[str, TicketRecord] = {}

    def create_ticket(self, device_id: str, user_id: str, ttl_seconds: Optional[int] = None) -> str:
        self.cleanup_expired()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        ticket_str = f"tkt_{secrets.token_urlsafe(32)}"
        now = time.time()
        record = TicketRecord(
            ticket=ticket_str,
            device_id=device_id,
            user_id=user_id,
            created_at=now,
            expires_at=now + ttl,
            consumed=False
        )
        self._tickets[ticket_str] = record
        audit_logger.log_event(
            event_type="ticket_created",
            user_id=user_id,
            device_id=device_id,
            outcome="success"
        )
        return ticket_str

    def consume_ticket(self, ticket_str: str) -> Optional[TicketRecord]:
        """
        Validates and consumes a ticket.
        Returns the TicketRecord on success.
        Returns None if ticket is invalid, expired, or already consumed.
        """
        self.cleanup_expired()
        record = self._tickets.get(ticket_str)
        if not record:
            audit_logger.log_event(
                event_type="ticket_consumed",
                outcome="rejected_not_found"
            )
            return None

        if record.consumed:
            audit_logger.log_event(
                event_type="ticket_consumed",
                user_id=record.user_id,
                device_id=record.device_id,
                outcome="rejected_already_consumed"
            )
            return None

        if time.time() > record.expires_at:
            audit_logger.log_event(
                event_type="ticket_consumed",
                user_id=record.user_id,
                device_id=record.device_id,
                outcome="rejected_expired"
            )
            self._tickets.pop(ticket_str, None)
            return None

        # Mark consumed
        record.consumed = True
        # Immediately pop or retain as consumed
        # Retaining with consumed=True ensures a replay attempt detects 'already_consumed' until cleanup
        audit_logger.log_event(
            event_type="ticket_consumed",
            user_id=record.user_id,
            device_id=record.device_id,
            outcome="success"
        )
        return record

    def cleanup_expired(self):
        now = time.time()
        expired_keys = [k for k, v in self._tickets.items() if now > v.expires_at + 10.0]
        for k in expired_keys:
            self._tickets.pop(k, None)

ticket_manager = TicketManager(default_ttl_seconds=settings.WS_TICKET_EXPIRE_SECONDS)
