import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings


logger = logging.getLogger(__name__)


async def send_auth_email(to_email: str, subject: str, body: str) -> None:
    if not settings.email_delivery_configured:
        if settings.debug:
            logger.info("Development auth email for %s: %s", to_email, body)
            return
        raise RuntimeError("Email delivery is not configured")

    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_starttls,
        use_tls=settings.smtp_use_tls,
        timeout=15,
    )
