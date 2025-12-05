"""Token notification service for low token warnings."""

import logging
import uuid
from datetime import date
from typing import Dict

from sqlalchemy.orm import Session

from app.models.user_token_usage import UserTokenUsage
from app.workshops.models import Workshop
from app.models.user import User


logger = logging.getLogger("app.services.token_notifications")


class TokenNotificationService:
    """Sends notifications for token usage warnings."""
    
    TOKEN_WARNING_THRESHOLDS = {
        "workshop": {
            "critical": 0.10,  # 10% remaining
            "warning": 0.25,   # 25% remaining
        },
        "user": {
            "critical": 0.10,
            "warning": 0.25,
        },
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_and_notify(
        self,
        user_id: uuid.UUID,
        workshop_id: uuid.UUID,
    ) -> Dict[str, list]:
        """
        Check token levels and return notifications if needed.
        
        Returns:
            Dict with "workshop_notifications" and "user_notifications" lists
        """
        notifications = {
            "workshop_notifications": [],
            "user_notifications": [],
        }
        
        # Check workshop tokens
        workshop = (
            self.db.query(Workshop)
            .filter(Workshop.id == workshop_id)
            .first()
        )
        
        if workshop:
            remaining_ratio = (
                (workshop.monthly_token_limit - workshop.tokens_used_this_month)
                / workshop.monthly_token_limit
                if workshop.monthly_token_limit > 0
                else 1.0
            )
            
            if remaining_ratio <= self.TOKEN_WARNING_THRESHOLDS["workshop"]["critical"]:
                notifications["workshop_notifications"].append({
                    "type": "critical",
                    "message": f"Workshop has {remaining_ratio*100:.1f}% tokens remaining ({workshop.monthly_token_limit - workshop.tokens_used_this_month:,} tokens)",
                    "remaining": workshop.monthly_token_limit - workshop.tokens_used_this_month,
                    "reset_date": workshop.token_reset_date.isoformat() if workshop.token_reset_date else None,
                })
            elif remaining_ratio <= self.TOKEN_WARNING_THRESHOLDS["workshop"]["warning"]:
                notifications["workshop_notifications"].append({
                    "type": "warning",
                    "message": f"Workshop has {remaining_ratio*100:.1f}% tokens remaining",
                    "remaining": workshop.monthly_token_limit - workshop.tokens_used_this_month,
                    "reset_date": workshop.token_reset_date.isoformat() if workshop.token_reset_date else None,
                })
        
        # Check user tokens
        usage = (
            self.db.query(UserTokenUsage)
            .filter(
                UserTokenUsage.user_id == user_id,
                UserTokenUsage.workshop_id == workshop_id,
                UserTokenUsage.date == date.today(),
            )
            .first()
        )
        
        if usage and usage.daily_limit:
            remaining_ratio = (
                (usage.daily_limit - usage.total_tokens_today) / usage.daily_limit
                if usage.daily_limit > 0
                else 1.0
            )
            
            if remaining_ratio <= self.TOKEN_WARNING_THRESHOLDS["user"]["critical"]:
                notifications["user_notifications"].append({
                    "type": "critical",
                    "message": f"You have {remaining_ratio*100:.1f}% of your daily limit remaining ({usage.daily_limit - usage.total_tokens_today:,} tokens)",
                    "remaining": usage.daily_limit - usage.total_tokens_today,
                    "limit": usage.daily_limit,
                })
            elif remaining_ratio <= self.TOKEN_WARNING_THRESHOLDS["user"]["warning"]:
                notifications["user_notifications"].append({
                    "type": "warning",
                    "message": f"You have {remaining_ratio*100:.1f}% of your daily limit remaining",
                    "remaining": usage.daily_limit - usage.total_tokens_today,
                    "limit": usage.daily_limit,
                })
        
        return notifications
    
    def send_notification(
        self,
        user_id: uuid.UUID,
        notification_type: str,
        message: str,
        details: dict = None,
    ) -> None:
        """
        Send notification (in-app, email, etc.).
        
        For now, we'll log it. In production, this would:
        - Store in notifications table
        - Send email if critical
        - Push to frontend via WebSocket
        """
        logger.warning(
            "Token notification: user_id=%s, type=%s, message=%s",
            user_id,
            notification_type,
            message,
        )
        
        # TODO: Implement actual notification delivery
        # - Store in notifications table
        # - Send via WebSocket to connected clients
        # - Send email for critical notifications

