"""Token accounting service for workshop and user-level token management."""

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.user_token_usage import UserTokenUsage
from app.workshops.models import Workshop
from app.workshops.models import WorkshopMember


logger = logging.getLogger("app.tokens.accounting")


class TokenAccountingService:
    """Manages token accounting at workshop and user levels."""

    def __init__(self, db: Session):
        self.db = db

    def check_workshop_limits(self, workshop_id: uuid.UUID, tokens_needed: int) -> bool:
        """Check if workshop has enough tokens remaining this month."""
        workshop = (
            self.db.query(Workshop)
            .filter(
                Workshop.id == workshop_id,
                Workshop.is_active.is_(True),
            )
            .first()
        )
        
        if not workshop:
            return False
        
        # Check if monthly reset is needed
        self._check_and_reset_monthly(workshop)
        
        remaining = workshop.monthly_token_limit - workshop.tokens_used_this_month
        return remaining >= tokens_needed

    def check_user_limits(
        self,
        user_id: uuid.UUID,
        workshop_id: uuid.UUID,
        tokens_needed: int,
    ) -> bool:
        """Check if user has enough tokens remaining (daily + role-based)."""
        # Get user's role in workshop
        membership = (
            self.db.query(WorkshopMember)
            .filter(
                WorkshopMember.user_id == user_id,
                WorkshopMember.workshop_id == workshop_id,
                WorkshopMember.is_active.is_(True),
            )
            .first()
        )
        
        if not membership:
            return False
        
        # Owners and admins have unlimited tokens
        if membership.role in ["owner", "admin"]:
            return True
        
        # Viewers have no AI access
        if membership.role == "viewer":
            return False
        
        # Get or create user token usage record
        usage = self._get_or_create_user_usage(user_id, workshop_id)
        
        # Check daily limit
        if usage.daily_limit and usage.total_tokens_today + tokens_needed > usage.daily_limit:
            return False
        
        # Check monthly limit
        if usage.monthly_limit and usage.total_tokens_month + tokens_needed > usage.monthly_limit:
            return False
        
        return True

    def reserve_tokens(
        self,
        user_id: uuid.UUID,
        workshop_id: uuid.UUID,
        tokens: int,
    ) -> bool:
        """
        Reserve tokens before AI call (optimistic locking).
        Returns True if reservation successful, False otherwise.
        """
        # Check limits first
        if not self.check_workshop_limits(workshop_id, tokens):
            return False
        
        if not self.check_user_limits(user_id, workshop_id, tokens):
            return False
        
        # Reservation is implicit - we'll record actual usage after AI call
        return True

    def record_token_usage(
        self,
        user_id: uuid.UUID,
        workshop_id: uuid.UUID,
        input_tokens: int,
        output_tokens: int,
        model: str = "gpt-4o-mini",
    ) -> None:
        """Record actual token usage after AI call."""
        total_tokens = input_tokens + output_tokens
        
        # Update workshop usage
        workshop = (
            self.db.query(Workshop)
            .filter(Workshop.id == workshop_id)
            .first()
        )
        
        if workshop:
            # Check and reset if needed
            self._check_and_reset_monthly(workshop)
            
            workshop.tokens_used_this_month += total_tokens
            self.db.add(workshop)
        
        # Update user usage
        usage = self._get_or_create_user_usage(user_id, workshop_id)
        
        # Check if date changed (daily reset)
        today = date.today()
        if usage.date != today:
            # Reset daily counters
            usage.date = today
            usage.input_tokens_today = 0
            usage.output_tokens_today = 0
            usage.total_tokens_today = 0
        
        # Update daily counters
        usage.input_tokens_today += input_tokens
        usage.output_tokens_today += output_tokens
        usage.total_tokens_today += total_tokens
        
        # Update monthly counters
        usage.input_tokens_month += input_tokens
        usage.output_tokens_month += output_tokens
        usage.total_tokens_month += total_tokens
        
        usage.last_used_at = datetime.utcnow()
        
        self.db.add(usage)
        self.db.commit()
        
        logger.info(
            "Token usage recorded: user=%s, workshop=%s, input=%d, output=%d, total=%d",
            user_id,
            workshop_id,
            input_tokens,
            output_tokens,
            total_tokens,
        )

    def get_user_remaining_tokens(
        self,
        user_id: uuid.UUID,
        workshop_id: uuid.UUID,
    ) -> Dict[str, any]:
        """Get remaining tokens for user (daily and monthly)."""
        usage = self._get_or_create_user_usage(user_id, workshop_id)
        
        workshop = (
            self.db.query(Workshop)
            .filter(Workshop.id == workshop_id)
            .first()
        )
        
        # Get user role
        membership = (
            self.db.query(WorkshopMember)
            .filter(
                WorkshopMember.user_id == user_id,
                WorkshopMember.workshop_id == workshop_id,
            )
            .first()
        )
        
        is_unlimited = membership and membership.role in ["owner", "admin"]
        
        return {
            "user": {
                "daily_limit": None if is_unlimited else usage.daily_limit,
                "daily_used": usage.total_tokens_today,
                "daily_remaining": None if is_unlimited else (usage.daily_limit - usage.total_tokens_today) if usage.daily_limit else None,
                "monthly_limit": None if is_unlimited else usage.monthly_limit,
                "monthly_used": usage.total_tokens_month,
                "monthly_remaining": None if is_unlimited else (usage.monthly_limit - usage.total_tokens_month) if usage.monthly_limit else None,
                "is_unlimited": is_unlimited,
            },
            "workshop": {
                "monthly_limit": workshop.monthly_token_limit if workshop else 0,
                "monthly_used": workshop.tokens_used_this_month if workshop else 0,
                "monthly_remaining": (workshop.monthly_token_limit - workshop.tokens_used_this_month) if workshop else 0,
                "reset_date": workshop.token_reset_date.isoformat() if workshop and workshop.token_reset_date else None,
            },
        }

    def _get_or_create_user_usage(
        self,
        user_id: uuid.UUID,
        workshop_id: uuid.UUID,
    ) -> UserTokenUsage:
        """Get or create user token usage record for today."""
        today = date.today()
        
        usage = (
            self.db.query(UserTokenUsage)
            .filter(
                UserTokenUsage.user_id == user_id,
                UserTokenUsage.workshop_id == workshop_id,
                UserTokenUsage.date == today,
            )
            .first()
        )
        
        if not usage:
            # Calculate daily limit based on role and workshop allocation
            daily_limit = self._calculate_daily_limit(user_id, workshop_id)
            monthly_limit = self._calculate_monthly_limit(user_id, workshop_id)
            
            usage = UserTokenUsage(
                user_id=user_id,
                workshop_id=workshop_id,
                date=today,
                daily_limit=daily_limit,
                monthly_limit=monthly_limit,
                created_by=str(user_id),
            )
            self.db.add(usage)
            self.db.flush()
        
        return usage

    def _calculate_daily_limit(
        self,
        user_id: uuid.UUID,
        workshop_id: uuid.UUID,
    ) -> Optional[int]:
        """Calculate user's daily limit from workshop pool."""
        membership = (
            self.db.query(WorkshopMember)
            .filter(
                WorkshopMember.user_id == user_id,
                WorkshopMember.workshop_id == workshop_id,
            )
            .first()
        )
        
        if not membership or membership.role in ["owner", "admin"]:
            return None  # Unlimited
        
        if membership.role == "viewer":
            return 0  # No AI access
        
        workshop = (
            self.db.query(Workshop)
            .filter(Workshop.id == workshop_id)
            .first()
        )
        
        if not workshop:
            return None
        
        # Distribute workshop daily limit among technicians
        daily_workshop_limit = workshop.monthly_token_limit // 30
        
        # Count active technicians in workshop
        technician_count = (
            self.db.query(WorkshopMember)
            .filter(
                WorkshopMember.workshop_id == workshop_id,
                WorkshopMember.role == "technician",
                WorkshopMember.is_active.is_(True),
            )
            .count()
        )
        
        if technician_count == 0:
            return daily_workshop_limit
        
        # Fair distribution
        return max(1, daily_workshop_limit // technician_count)

    def _calculate_monthly_limit(
        self,
        user_id: uuid.UUID,
        workshop_id: uuid.UUID,
    ) -> Optional[int]:
        """Calculate user's monthly limit from workshop pool."""
        membership = (
            self.db.query(WorkshopMember)
            .filter(
                WorkshopMember.user_id == user_id,
                WorkshopMember.workshop_id == workshop_id,
            )
            .first()
        )
        
        if not membership or membership.role in ["owner", "admin"]:
            return None  # Unlimited
        
        if membership.role == "viewer":
            return 0  # No AI access
        
        workshop = (
            self.db.query(Workshop)
            .filter(Workshop.id == workshop_id)
            .first()
        )
        
        if not workshop:
            return None
        
        # Distribute workshop monthly limit among technicians
        technician_count = (
            self.db.query(WorkshopMember)
            .filter(
                WorkshopMember.workshop_id == workshop_id,
                WorkshopMember.role == "technician",
                WorkshopMember.is_active.is_(True),
            )
            .count()
        )
        
        if technician_count == 0:
            return workshop.monthly_token_limit
        
        # Fair distribution
        return max(1, workshop.monthly_token_limit // technician_count)

    def _check_and_reset_monthly(self, workshop: Workshop) -> None:
        """Check if monthly reset is needed and reset if so."""
        today = date.today()
        
        # Initialize reset date if not set
        if not workshop.token_reset_date:
            # Set to next month, same day
            if today.day >= workshop.token_reset_day:
                # This month's reset day has passed, set to next month
                next_month = today.replace(day=1) + timedelta(days=32)
                workshop.token_reset_date = next_month.replace(day=min(workshop.token_reset_day, 28))
            else:
                # This month's reset day hasn't passed yet
                workshop.token_reset_date = today.replace(day=min(workshop.token_reset_day, 28))
            self.db.add(workshop)
            self.db.flush()
        
        # Check if reset is needed
        if workshop.token_reset_date <= today:
            logger.info("Resetting monthly tokens for workshop %s", workshop.id)
            workshop.tokens_used_this_month = 0
            
            # Set next reset date
            next_month = today.replace(day=1) + timedelta(days=32)
            workshop.token_reset_date = next_month.replace(day=min(workshop.token_reset_day, 28))
            
            self.db.add(workshop)
            self.db.commit()

    def reset_daily_limits(self) -> None:
        """Reset daily limits for all users (run via cron)."""
        today = date.today()
        
        # This is handled automatically when recording usage
        # But we can also explicitly reset old records
        old_records = (
            self.db.query(UserTokenUsage)
            .filter(UserTokenUsage.date < today)
            .all()
        )
        
        for record in old_records:
            if record.date < today:
                # Reset daily counters (keep monthly)
                record.input_tokens_today = 0
                record.output_tokens_today = 0
                record.total_tokens_today = 0
                record.date = today
                self.db.add(record)
        
        self.db.commit()
        logger.info("Reset daily token limits for %d records", len(old_records))

    def reset_monthly_limits(self) -> None:
        """Reset monthly limits for workshops (run via cron)."""
        today = date.today()
        
        workshops_to_reset = (
            self.db.query(Workshop)
            .filter(
                Workshop.token_reset_date <= today,
                Workshop.is_active.is_(True),
            )
            .all()
        )
        
        for workshop in workshops_to_reset:
            self._check_and_reset_monthly(workshop)
        
        logger.info("Reset monthly token limits for %d workshops", len(workshops_to_reset))

