from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_auth_event(
    db: Session,
    *,
    user_id: Optional[str],
    action_type: str,
    success: bool,
    ip_address: Optional[str],
    user_agent: Optional[str],
    details: Optional[dict[str, Any]] = None,
) -> None:
    log = AuditLog(
        user_id=user_id,
        action_type=action_type,
        resource_type="auth",
        resource_id=None,
        details={"success": success, **(details or {})},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.commit()


