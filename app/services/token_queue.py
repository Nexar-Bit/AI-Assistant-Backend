"""Token queue system for requests when limits are reached."""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

from app.core.redis import get_redis_client, is_redis_available


logger = logging.getLogger("app.services.token_queue")


@dataclass
class QueueTicket:
    """Represents a queued request ticket."""
    
    ticket_id: str
    user_id: str
    workshop_id: str
    request_data: dict
    created_at: datetime
    estimated_tokens: int


class TokenQueue:
    """Queue system for requests when token limits are reached."""
    
    QUEUE_PREFIX = "token_queue:"
    TICKET_PREFIX = "token_ticket:"
    TTL_SECONDS = 3600  # 1 hour
    
    def __init__(self):
        self.redis = get_redis_client()
    
    def enqueue_request(
        self,
        user_id: uuid.UUID,
        workshop_id: uuid.UUID,
        request_data: dict,
        estimated_tokens: int,
    ) -> QueueTicket:
        """Add request to queue."""
        if not is_redis_available() or not self.redis:
            raise RuntimeError("Redis is not available. Queue system requires Redis.")
        
        ticket_id = str(uuid.uuid4())
        ticket = QueueTicket(
            ticket_id=ticket_id,
            user_id=str(user_id),
            workshop_id=str(workshop_id),
            request_data=request_data,
            created_at=datetime.utcnow(),
            estimated_tokens=estimated_tokens,
        )
        
        # Store ticket data
        ticket_key = f"{self.TICKET_PREFIX}{ticket_id}"
        ticket_data = {
            "user_id": ticket.user_id,
            "workshop_id": ticket.workshop_id,
            "request_data": json.dumps(request_data),
            "estimated_tokens": estimated_tokens,
            "created_at": ticket.created_at.isoformat(),
        }
        self.redis.hset(ticket_key, mapping=ticket_data)
        self.redis.expire(ticket_key, self.TTL_SECONDS)
        
        # Add to queue (sorted set by timestamp)
        queue_key = f"{self.QUEUE_PREFIX}{workshop_id}"
        score = datetime.utcnow().timestamp()
        self.redis.zadd(queue_key, {ticket_id: score})
        self.redis.expire(queue_key, self.TTL_SECONDS)
        
        logger.info(
            "Request queued: ticket_id=%s, user_id=%s, workshop_id=%s, tokens=%d",
            ticket_id,
            user_id,
            workshop_id,
            estimated_tokens,
        )
        
        return ticket
    
    def dequeue_request(self, workshop_id: uuid.UUID) -> Optional[QueueTicket]:
        """Get next request from queue when tokens available."""
        if not is_redis_available() or not self.redis:
            return None
        
        queue_key = f"{self.QUEUE_PREFIX}{workshop_id}"
        
        # Get oldest ticket
        tickets = self.redis.zrange(queue_key, 0, 0, withscores=True)
        if not tickets:
            return None
        
        ticket_id = tickets[0][0].decode() if isinstance(tickets[0][0], bytes) else tickets[0][0]
        
        # Get ticket data
        ticket_key = f"{self.TICKET_PREFIX}{ticket_id}"
        ticket_data = self.redis.hgetall(ticket_key)
        
        if not ticket_data:
            # Ticket expired or missing, remove from queue
            self.redis.zrem(queue_key, ticket_id)
            return None
        
        # Decode bytes to strings if needed
        if isinstance(ticket_data.get("user_id"), bytes):
            ticket_data = {k.decode(): v.decode() if isinstance(v, bytes) else v for k, v in ticket_data.items()}
        
        # Remove from queue
        self.redis.zrem(queue_key, ticket_id)
        self.redis.delete(ticket_key)
        
        ticket = QueueTicket(
            ticket_id=ticket_id,
            user_id=ticket_data["user_id"],
            workshop_id=ticket_data["workshop_id"],
            request_data=json.loads(ticket_data["request_data"]),
            created_at=datetime.fromisoformat(ticket_data["created_at"]),
            estimated_tokens=int(ticket_data["estimated_tokens"]),
        )
        
        logger.info("Request dequeued: ticket_id=%s", ticket_id)
        return ticket
    
    def get_queue_position(self, ticket_id: str, workshop_id: uuid.UUID) -> int:
        """Get position in queue (0 = next, -1 = not found)."""
        if not is_redis_available() or not self.redis:
            return -1
        
        queue_key = f"{self.QUEUE_PREFIX}{workshop_id}"
        position = self.redis.zrank(queue_key, ticket_id)
        
        if position is None:
            return -1
        
        return position
    
    def estimate_wait_time(self, ticket_id: str, workshop_id: uuid.UUID) -> int:
        """Estimate wait time in seconds."""
        position = self.get_queue_position(ticket_id, workshop_id)
        if position < 0:
            return 0
        
        # Rough estimate: 30 seconds per request ahead
        return position * 30
    
    def remove_ticket(self, ticket_id: str, workshop_id: uuid.UUID) -> bool:
        """Remove ticket from queue (e.g., if user cancels)."""
        if not is_redis_available() or not self.redis:
            return False
        
        queue_key = f"{self.QUEUE_PREFIX}{workshop_id}"
        ticket_key = f"{self.TICKET_PREFIX}{ticket_id}"
        
        removed = self.redis.zrem(queue_key, ticket_id)
        self.redis.delete(ticket_key)
        
        return removed > 0
    
    def get_queue_size(self, workshop_id: uuid.UUID) -> int:
        """Get number of requests in queue."""
        if not is_redis_available() or not self.redis:
            return 0
        
        queue_key = f"{self.QUEUE_PREFIX}{workshop_id}"
        return self.redis.zcard(queue_key)


# Global queue instance
token_queue = TokenQueue()

