from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.consultation import Consultation
from app.models.user import User


def get_user_tokens_used_today(db: Session, user_id: str) -> int:
    today = date.today()
    stmt = (
        select(func.coalesce(func.sum(Consultation.total_tokens), 0))
        .where(Consultation.user_id == user_id)
        .where(func.date(Consultation.created_at) == today)
    )
    result = db.execute(stmt).scalar_one()
    return int(result or 0)


def ensure_within_daily_limit(db: Session, user: User, tokens_to_add: int) -> None:
    used = get_user_tokens_used_today(db, str(user.id))
    if used + tokens_to_add > user.daily_token_limit:
        raise PermissionError("Daily token limit exceeded for this user.")


