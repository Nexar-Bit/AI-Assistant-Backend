"""Email service stub for registration/approval notifications.

This implementation keeps the interface used by the API but does not
actually send emails unless SMTP is fully configured. In our current
setup, email verification has been disabled, so these methods are
essentially no-ops that log what would have been sent.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings


logger = logging.getLogger("app.services.email")


class EmailService:
    """Service for sending emails via SMTP (stubbed / optional)."""

    def __init__(self) -> None:
        # Keep the same config shape as the original implementation
        self.smtp_host: Optional[str] = getattr(settings, "SMTP_HOST", None)
        self.smtp_port: Optional[int] = getattr(settings, "SMTP_PORT", None)
        self.smtp_user: Optional[str] = getattr(settings, "SMTP_USER", None)
        self.smtp_password: Optional[str] = getattr(settings, "SMTP_PASSWORD", None)
        self.from_email: Optional[str] = getattr(settings, "SMTP_FROM_EMAIL", None) or self.smtp_user
        self.from_name: Optional[str] = getattr(settings, "SMTP_FROM_NAME", None)

        # Email is considered enabled only if basic SMTP config is present
        self.enabled: bool = bool(self.smtp_host and self.smtp_user and self.smtp_password)

    def is_available(self) -> bool:
        """Return True if email sending is configured and enabled."""
        return self.enabled

    # The following methods mirror the interface used in the API modules.
    # They don't raise if email isn't configured; they just log and return False.

    def send_verification_email(self, to_email: str, verification_token: str, username: str) -> bool:
        """Previously used for email verification. Now a no-op for compatibility."""
        if not self.enabled:
            logger.info(
                "send_verification_email called for %s, but email service is disabled. "
                "Email verification is no longer required.",
                to_email,
            )
            return False

        # If in the future SMTP is configured and you want to actually send,
        # you can implement real sending logic here.
        logger.info("send_verification_email would be sent to %s (token=%s)", to_email, verification_token)
        return True

    def send_registration_notification(
        self,
        to_email: str,
        username: str,
        email: str,
        message: Optional[str],
        user_id: str,
    ) -> bool:
        """Notify platform admin of a new registration request (optional)."""
        if not self.enabled:
            logger.info(
                "send_registration_notification called for admin %s but email service is disabled. "
                "Details: username=%s email=%s user_id=%s",
                to_email,
                username,
                email,
                user_id,
            )
            return False

        logger.info(
            "send_registration_notification would be sent to admin %s for user %s (%s, id=%s)",
            to_email,
            username,
            email,
            user_id,
        )
        return True

    def send_approval_email(self, to_email: str, username: str, approved: bool) -> bool:
        """Notify user that their registration was approved or rejected."""
        if not self.enabled:
            logger.info(
                "send_approval_email called for %s but email service is disabled. "
                "approved=%s username=%s",
                to_email,
                approved,
                username,
            )
            return False

        logger.info(
            "send_approval_email would be sent to %s (username=%s, approved=%s)",
            to_email,
            username,
            approved,
        )
        return True


# Singleton instance used by the rest of the app
email_service = EmailService()


