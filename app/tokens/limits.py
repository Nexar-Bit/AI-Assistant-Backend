"""Token limits service for managing usage limits."""

import logging
from typing import Optional
from datetime import date

from sqlalchemy.orm import Session

from app.models.user_token_usage import UserTokenUsage
from app.workshops.models import Workshop

logger = logging.getLogger("app.tokens.limits")


class TokenLimitsService:
    """Manages token usage limits at workshop and user levels."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_daily_limit(
        self,
        user_id: str,
        workshop_id: str,
    ) -> Optional[int]:
        """Get user's daily token limit for a workshop."""
        usage = (
            self.db.query(UserTokenUsage)
            .filter(
                UserTokenUsage.user_id == user_id,
                UserTokenUsage.workshop_id == workshop_id,
                UserTokenUsage.date == date.today(),
            )
            .first()
        )
        
        if usage:
            return usage.daily_limit
        
        # Default limit if not set
        return 10000  # 10k tokens per day default
    
    def get_workshop_monthly_limit(self, workshop_id: str) -> int:
        """Get workshop's monthly token limit."""
        workshop = self.db.query(Workshop).filter(Workshop.id == workshop_id).first()
        if workshop:
            return workshop.monthly_token_limit or 100000  # 100k default
        
        return 100000

