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
            "subject": "Welcome to AI Mentor!",
            "html": (
                f"<h2>Welcome to AI Mentor!</h2>"
                f"<p>Your workspace <strong>{slug}</strong> is ready.</p>"
                f"<p>Upload your product documentation, connect MCP to your IDE, "
                f"and start getting AI-powered answers about your APIs.</p>"
                f"<p>— AI Mentor Team</p>"
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
            "subject": "Verify your AI Mentor email",
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


def send_guest_approval_request(admin_email: str, guest_email: str, token: str) -> None:
    """Send a verification/approval link to the admin for a guest account."""
    _init_resend()
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured, skipping guest approval email")
        return
    verify_url = f"{settings.app_base_url}/verify-email?token={token}"
    try:
        resend.Emails.send({
            "from": settings.email_from,
            "to": [admin_email],
            "subject": f"AI Mentor: approve registration for {guest_email}",
            "html": (
                f"<h2>Guest Registration Approval</h2>"
                f"<p>A new guest account has requested access:</p>"
                f"<p><strong>{guest_email}</strong></p>"
                f"<p>Click below to approve and verify this account:</p>"
                f"<p><a href=\"{verify_url}\">Approve Registration</a></p>"
                f"<p>This link expires in 24 hours. "
                f"If you didn't expect this request, ignore this email.</p>"
            ),
        })
        logger.info("Guest approval email sent", extra={"admin": admin_email, "guest": guest_email})
    except Exception:
        logger.warning("Failed to send guest approval email", exc_info=True)


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
            "subject": "Reset your AI Mentor password",
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
