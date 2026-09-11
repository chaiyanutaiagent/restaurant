from __future__ import annotations

from email.message import EmailMessage
from html import escape
import hashlib
import logging
from urllib.parse import quote

import aiosmtplib

from app.config import settings


logger = logging.getLogger(__name__)


def _recipient_reference(recipient: str) -> str:
    return hashlib.sha256(recipient.encode("utf-8")).hexdigest()[:12]


async def deliver_membership_email(
    *,
    recipient: str,
    purpose: str,
    token: str,
) -> bool:
    if purpose == "verify_email":
        subject = "ยืนยันอีเมล Restaurant SaaS"
        path = f"/verify-email#token={quote(token, safe='')}"
        heading = "ยืนยันอีเมลของคุณ"
        detail = "เปิดลิงก์นี้เพื่อเริ่มช่วงทดลองใช้ Restaurant SaaS"
    elif purpose == "reset_password":
        subject = "ตั้งรหัสผ่าน Restaurant SaaS ใหม่"
        path = f"/reset-password#token={quote(token, safe='')}"
        heading = "ตั้งรหัสผ่านใหม่"
        detail = "หากคุณไม่ได้ขอเปลี่ยนรหัสผ่าน ให้ละเว้นอีเมลฉบับนี้"
    else:
        raise ValueError("Unsupported SaaS account email purpose")

    action_url = f"{settings.saas_public_base_url}{path}"
    if settings.saas_email_delivery_mode == "console":
        logger.info(
            "SaaS account email accepted by console transport: purpose=%s recipient_ref=%s",
            purpose,
            _recipient_reference(recipient),
        )
        return True

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = (
        f"{settings.saas_smtp_from_name} <{settings.saas_smtp_from_email}>"
    )
    message["To"] = recipient
    message.set_content(f"{heading}\n\n{detail}\n\n{action_url}")
    message.add_alternative(
        "<h2>{}</h2><p>{}</p><p><a href=\"{}\">ดำเนินการต่อ</a></p>".format(
            escape(heading),
            escape(detail),
            escape(action_url, quote=True),
        ),
        subtype="html",
    )
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.saas_smtp_host,
            port=settings.saas_smtp_port,
            username=settings.saas_smtp_username,
            password=settings.saas_smtp_password,
            use_tls=settings.saas_smtp_use_tls,
            start_tls=settings.saas_smtp_start_tls,
            timeout=15,
        )
        return True
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning(
            "SaaS account email delivery failed: purpose=%s recipient_ref=%s error=%s",
            purpose,
            _recipient_reference(recipient),
            type(exc).__name__,
        )
        return False
