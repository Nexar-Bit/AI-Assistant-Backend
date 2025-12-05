"""Token alerts service for low token warnings."""

import logging
from typing import Dict, List
from datetime import date

from sqlalchemy.orm import Session

from app.models.user_token_usage import UserTokenUsage
from app.workshops.models import Workshop

logger = logging.getLogger("app.tokens.alerts")


class TokenAlertService:
    """Sends alerts for low token balances."""
    
    WARNING_THRESHOLD = 0.25  # 25% remaining
    CRITICAL_THRESHOLD = 0.10  # 10% remaining
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_workshop_alerts(self, workshop_id: str) -> List[Dict]:
        """Check if workshop needs token alerts."""
        workshop = self.db.query(Workshop).filter(Workshop.id == workshop_id).first()
        if not workshop:
            return []
        
        remaining = workshop.monthly_token_limit - workshop.tokens_used_this_month
        ratio = remaining / workshop.monthly_token_limit if workshop.monthly_token_limit > 0 else 1.0
        
        alerts = []
        if ratio <= self.CRITICAL_THRESHOLD:
            alerts.append({
                "type": "critical",
                "message": f"Workshop has {ratio*100:.1f}% tokens remaining",
                "remaining": remaining,
            })
        elif ratio <= self.WARNING_THRESHOLD:
            alerts.append({
                "type": "warning",
                "message": f"Workshop has {ratio*100:.1f}% tokens remaining",
                "remaining": remaining,
            })
        
        return alerts
    
    def check_user_alerts(
        self,
        user_id: str,
        workshop_id: str,
    ) -> List[Dict]:
        """Check if user needs token alerts."""
        usage = (
            self.db.query(UserTokenUsage)
            .filter(
                UserTokenUsage.user_id == user_id,
                UserTokenUsage.workshop_id == workshop_id,
                UserTokenUsage.date == date.today(),
            )
            .first()
        )
        
        if not usage or not usage.daily_limit:
            return []
        
        remaining = usage.daily_limit - usage.total_tokens_today
        ratio = remaining / usage.daily_limit if usage.daily_limit > 0 else 1.0
        
        alerts = []
        if ratio <= self.CRITICAL_THRESHOLD:
            alerts.append({
                "type": "critical",
                "message": f"You have {ratio*100:.1f}% of your daily limit remaining",
                "remaining": remaining,
            })
        elif ratio <= self.WARNING_THRESHOLD:
            alerts.append({
                "type": "warning",
                "message": f"You have {ratio*100:.1f}% of your daily limit remaining",
                "remaining": remaining,
            })
        
        return alerts

