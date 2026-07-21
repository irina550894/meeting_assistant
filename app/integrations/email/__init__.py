"""Email notification integration."""

from app.integrations.email.notifier import SmtpUserEmailSender, UserEmailNotifier

__all__ = ["SmtpUserEmailSender", "UserEmailNotifier"]
