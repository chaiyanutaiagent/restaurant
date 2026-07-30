from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_gateway import NotificationLog, PaymentGatewayConfig
from app.models.settings import BranchSettings
from app.services.payment_gateway_service import PaymentGatewayService

logger = logging.getLogger(__name__)

TEMPLATES = {
    "sale.created": {
        "line": "🛍️ มีออเดอร์ใหม่!\nเลขที่: {order_number}\nยอด: ฿{total_amount}\nสาขา: {branch_name}",
        "email_subject": "ออเดอร์ใหม่ {order_number}",
        "email_body": """
          <h2>มีออเดอร์ใหม่เข้ามา</h2>
          <p>เลขที่ออเดอร์: <strong>{order_number}</strong></p>
          <p>ยอดรวม: <strong>฿{total_amount}</strong></p>
          <p>สาขา: {branch_name}</p>
          <p>เวลา: {created_at}</p>
        """,
    },
    "stock.low": {
        "line": "⚠️ สต็อกต่ำ!\nสินค้า: {product_name}\nSKU: {sku}\nคงเหลือ: {qty_on_hand}\nจุดสั่งซื้อ: {min_stock_qty}",
        "email_subject": "แจ้งเตือน: สต็อกสินค้าต่ำ — {product_name}",
        "email_body": """
          <h2>⚠️ สต็อกสินค้าต่ำกว่าเกณฑ์</h2>
          <p>สินค้า: <strong>{product_name}</strong> (SKU: {sku})</p>
          <p>จำนวนคงเหลือ: <strong>{qty_on_hand}</strong></p>
          <p>จุดสั่งซื้อขั้นต่ำ: {min_stock_qty}</p>
        """,
    },
    "stock.negative": {
        "line": "🚨 สต็อกหน้าร้านติดลบ!\nสินค้า: {product_name}\nSKU: {sku}\nก่อนขาย: {qty_before}\nหลังขาย: {qty_after}\nใบขาย: {order_number}",
        "email_subject": "แจ้งเตือน: สต็อกหน้าร้านติดลบ — {product_name}",
        "email_body": """
          <h2>🚨 สต็อกหน้าร้านติดลบ</h2>
          <p>สินค้า: <strong>{product_name}</strong> (SKU: {sku})</p>
          <p>ก่อนขาย: {qty_before}</p>
          <p>หลังขาย: <strong>{qty_after}</strong></p>
          <p>ใบขาย: {order_number}</p>
        """,
    },
    "shipment.created": {
        "line": "📦 สร้างการจัดส่งแล้ว\nเลขที่: {shipment_number}\nผู้รับ: {recipient_name}\nขนส่ง: {carrier_name}\nเลขพัสดุ: {tracking_number}",
        "email_subject": "สร้างการจัดส่ง {shipment_number}",
        "email_body": """
          <h2>สร้างการจัดส่งสำเร็จ</h2>
          <p>เลขที่จัดส่ง: <strong>{shipment_number}</strong></p>
          <p>ผู้รับ: {recipient_name} ({recipient_phone})</p>
          <p>ขนส่ง: {carrier_name}</p>
          <p>เลขพัสดุ: <strong>{tracking_number}</strong></p>
        """,
    },
    "payroll.processed": {
        "line": "💰 ประมวลผลเงินเดือนแล้ว\nงวด: {period}\nพนักงาน: {total_employees} คน\nยอดสุทธิ: ฿{total_net}",
        "email_subject": "ประมวลผลเงินเดือน {period}",
        "email_body": """
          <h2>ประมวลผลเงินเดือนสำเร็จ</h2>
          <p>งวด: <strong>{period}</strong></p>
          <p>จำนวนพนักงาน: {total_employees} คน</p>
          <p>ยอดจ่ายสุทธิรวม: <strong>฿{total_net}</strong></p>
        """,
    },
}


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_config(self, company_id: uuid.UUID) -> PaymentGatewayConfig:
        return await PaymentGatewayService(self.db).get_config_decrypted(company_id)

    async def send_line_notify(
        self,
        token: str,
        message: str,
        company_id: uuid.UUID,
        event_type: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> bool:
        import httpx

        success = False
        error_message: str | None = None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://notify-api.line.me/api/notify",
                    headers={"Authorization": f"Bearer {token}"},
                    data={"message": message},
                    timeout=10.0,
                )
            success = resp.status_code == 200
            if not success:
                error_message = resp.text[:500]
        except Exception as exc:  # pragma: no cover - network failure path
            error_message = str(exc)
            logger.warning("line notify failed: %s", exc)

        await self._log(
            company_id,
            "line",
            token[:8] + "...",
            event_type,
            None,
            message,
            success,
            reference_type,
            reference_id,
            error_message,
        )
        return success

    async def send_email(
        self,
        config: PaymentGatewayConfig,
        to_email: str,
        subject: str,
        html_body: str,
        company_id: uuid.UUID,
        event_type: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> bool:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config.smtp_from_name or ''} <{config.smtp_from_email}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        success = False
        error_message: str | None = None
        try:
            await aiosmtplib.send(
                msg,
                hostname=config.smtp_host,
                port=int(config.smtp_port or 587),
                username=config.smtp_username,
                password=config.smtp_password,
                use_tls=int(config.smtp_port or 587) == 465,
                start_tls=int(config.smtp_port or 587) == 587,
                timeout=15,
            )
            success = True
        except Exception as exc:  # pragma: no cover - network failure path
            error_message = str(exc)
            logger.warning("smtp send failed: %s", exc)

        await self._log(
            company_id,
            "email",
            to_email,
            event_type,
            subject,
            html_body[:500],
            success,
            reference_type,
            reference_id,
            error_message,
        )
        return success

    async def notify_event(
        self,
        company_id: uuid.UUID,
        event_type: str,
        context: dict,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> None:
        template = TEMPLATES.get(event_type)
        if template is None:
            return

        config = await self.get_config(company_id)
        merged_context = {"created_at": datetime.now(timezone.utc).isoformat(), **context}
        try:
            if config.line_notify_enabled and config.line_notify_token:
                msg = template["line"].format(**merged_context)
                await self.send_line_notify(
                    config.line_notify_token,
                    msg,
                    company_id,
                    event_type,
                    reference_type,
                    reference_id,
                )

            if config.smtp_enabled and config.smtp_from_email and config.smtp_host:
                settings = await self.db.scalar(
                    select(BranchSettings)
                    .where(BranchSettings.company_id == company_id)
                    .limit(1)
                )
                if settings and settings.notify_low_stock_email:
                    subject = template["email_subject"].format(**merged_context)
                    body = template["email_body"].format(**merged_context)
                    await self.send_email(
                        config,
                        settings.notify_low_stock_email,
                        subject,
                        body,
                        company_id,
                        event_type,
                        reference_type,
                        reference_id,
                    )
        except Exception as exc:  # pragma: no cover - notification should never break business flow
            logger.warning("notify_event failed: %s", exc)

    async def _log(
        self,
        company_id: uuid.UUID,
        channel: str,
        recipient: str,
        event_type: str,
        subject: str | None,
        body: str,
        success: bool,
        reference_type: str | None = None,
        reference_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.db.add(
            NotificationLog(
                company_id=company_id,
                channel=channel,
                recipient=recipient,
                event_type=event_type,
                subject=subject,
                body=body,
                status="sent" if success else "failed",
                error_message=error_message,
                reference_type=reference_type,
                reference_id=reference_id,
            )
        )
