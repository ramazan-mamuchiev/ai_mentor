"""Send transactional emails via Resend."""

import logging

import resend

from app.config import settings

logger = logging.getLogger(__name__)


def _init_resend():
    if settings.resend_api_key:
        resend.api_key = settings.resend_api_key


def send_welcome_email(to: str, slug: str) -> None:
    _init_resend()
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured, skipping welcome email")
        return
    try:
        resend.Emails.send({
            "from": settings.email_from,
            "to": [to],
            "subject": "Welcome to Lexiro!",
            "html": (
                f"<h2>Welcome to Lexiro!</h2>"
                f"<p>Your workspace <strong>{slug}</strong> is ready.</p>"
                f"<p>Upload your product documentation, connect MCP to your IDE, "
                f"and start getting AI-powered answers about your APIs.</p>"
                f"<p>— Lexiro Team</p>"
            ),
        })
        logger.info("Welcome email sent", extra={"to": to})
    except Exception:
        logger.warning("Failed to send welcome email", exc_info=True)


def send_email_verification(to: str, token: str) -> None:
    _init_resend()
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured, skipping verification email")
        return
    verify_url = f"{settings.app_base_url}/verify-email?token={token}"
    try:
        resend.Emails.send({
            "from": settings.email_from,
            "to": [to],
            "subject": "Verify your Lexiro email",
            "html": (
                f"<h2>Verify your email</h2>"
                f"<p>Click the link below to verify your email address:</p>"
                f"<p><a href=\"{verify_url}\">{verify_url}</a></p>"
                f"<p>This link expires in 24 hours.</p>"
            ),
        })
        logger.info("Verification email sent", extra={"to": to})
    except Exception:
        logger.warning("Failed to send verification email", exc_info=True)


def send_password_reset(to: str, token: str) -> None:
    _init_resend()
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured, skipping password reset email")
        return
    reset_url = f"{settings.app_base_url}/reset-password?token={token}"
    try:
        resend.Emails.send({
            "from": settings.email_from,
            "to": [to],
            "subject": "Reset your Lexiro password",
            "html": (
                f"<h2>Password Reset</h2>"
                f"<p>Click the link below to reset your password:</p>"
                f"<p><a href=\"{reset_url}\">{reset_url}</a></p>"
                f"<p>This link expires in 1 hour. If you didn't request this, ignore this email.</p>"
            ),
        })
        logger.info("Password reset email sent", extra={"to": to})
    except Exception:
        logger.warning("Failed to send password reset email", exc_info=True)
