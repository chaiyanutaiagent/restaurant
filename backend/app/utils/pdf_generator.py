from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.models.company import Company
from app.models.etax import TaxDocument, TaxDocumentItem
from app.models.hr import PayrollItem, PayrollRun
from app.models.payable import APPayment, WHTCertificate
from app.models.purchase import GoodsReceipt, PurchaseOrder
from app.models.stock_count import StockCountItem, StockCountSession
from app.models.logistics import Shipment
from app.schemas.payable import APPaymentAllocationRead
from app.schemas.stock_count import VarianceReport
from app.utils.thai_date import MONTHS_TH, format_thai_date

TWOPLACES = Decimal("0.01")


def q2(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _css() -> str:
    return """
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@400;500;700&display=swap');
    @page { size: A4; margin: 16mm; @bottom-right { content: "หน้า " counter(page); font-size: 10px; color: #666; } }
    body { font-family: 'Sarabun', sans-serif; color: #1f2937; font-size: 12px; }
    h1, h2, h3, p { margin: 0; }
    .header, .section { margin-bottom: 16px; }
    .title { font-size: 24px; font-weight: 700; margin-bottom: 6px; }
    .subtitle { color: #4b5563; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
    .box { border: 1px solid #d1d5db; border-radius: 10px; padding: 10px 12px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }
    th { background: #f3f4f6; text-align: left; }
    .right { text-align: right; }
    .totals { width: 320px; margin-left: auto; margin-top: 12px; }
    .totals td { border: none; padding: 4px 0; }
    .totals .grand { font-size: 16px; font-weight: 700; border-top: 1px solid #9ca3af; padding-top: 8px; }
    .signatures { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-top: 24px; }
    .signature-box { border-top: 1px solid #9ca3af; padding-top: 10px; text-align: center; min-height: 52px; }
    """


def render_po_html(
    po: PurchaseOrder,
    company_name: str,
    company_address: str,
    company_tax_id: str,
) -> str:
    item_rows = []
    for index, item in enumerate(po.items, start=1):
        line_total = q2(Decimal(item.subtotal) + (Decimal(item.vat_amount) if item.vat_type == "excluded" else Decimal("0")))
        item_rows.append(
            f"""
            <tr>
              <td>{index}</td>
              <td>{item.product_name}</td>
              <td>{item.sku}</td>
              <td class="right">{Decimal(item.qty_ordered):,.2f}</td>
              <td>{item.unit_code or "-"}</td>
              <td class="right">{Decimal(item.unit_cost):,.2f}</td>
              <td class="right">{Decimal(item.discount_amount):,.2f}</td>
              <td class="right">{Decimal(item.subtotal):,.2f}</td>
              <td class="right">{Decimal(item.vat_amount):,.2f}</td>
              <td class="right">{line_total:,.2f}</td>
            </tr>
            """
        )

    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>{_css()}</style>
      </head>
      <body>
        <div class="header">
          <div class="title">ใบสั่งซื้อ / Purchase Order</div>
          <p><strong>{company_name}</strong></p>
          <p>{company_address or "-"}</p>
          <p>เลขประจำตัวผู้เสียภาษี: {company_tax_id or "-"}</p>
        </div>

        <div class="grid">
          <div class="box">
            <p><strong>เลขที่ PO:</strong> {po.po_number}</p>
            <p><strong>วันที่:</strong> {format_thai_date(po.created_at, "short")}</p>
            <p><strong>กำหนดรับ:</strong> {format_thai_date(po.created_at, "short") if po.expected_date is None else po.expected_date.strftime("%d/%m/%Y")}</p>
          </div>
          <div class="box">
            <p><strong>ผู้จำหน่าย:</strong> {po.supplier.name}</p>
            <p><strong>เลขผู้เสียภาษี:</strong> {po.supplier.tax_id or "-"}</p>
            <p><strong>เงื่อนไข:</strong> {po.supplier.payment_term_days} วัน</p>
          </div>
        </div>

        <div class="section">
          <table>
            <thead>
              <tr>
                <th>ลำดับ</th>
                <th>รายการ</th>
                <th>SKU</th>
                <th class="right">จำนวน</th>
                <th>หน่วย</th>
                <th class="right">ราคา/หน่วย</th>
                <th class="right">ส่วนลด</th>
                <th class="right">ก่อน VAT</th>
                <th class="right">VAT</th>
                <th class="right">รวม</th>
              </tr>
            </thead>
            <tbody>
              {''.join(item_rows)}
            </tbody>
          </table>
        </div>

        <table class="totals">
          <tr><td>ยอดรวม</td><td class="right">{Decimal(po.subtotal):,.2f}</td></tr>
          <tr><td>ส่วนลด</td><td class="right">{Decimal(po.discount_amount):,.2f}</td></tr>
          <tr><td>VAT</td><td class="right">{Decimal(po.vat_amount):,.2f}</td></tr>
          <tr><td>WHT</td><td class="right">- {Decimal(po.wht_amount):,.2f}</td></tr>
          <tr><td class="grand">ยอดสุทธิ</td><td class="right grand">{Decimal(po.total_amount):,.2f}</td></tr>
        </table>

        <div class="signatures">
          <div class="signature-box">ผู้สั่งซื้อ</div>
          <div class="signature-box">ผู้อนุมัติ</div>
          <div class="signature-box">ผู้จำหน่าย</div>
        </div>
      </body>
    </html>
    """


def render_gr_html(
    gr: GoodsReceipt,
    po: PurchaseOrder,
    company_name: str,
    company_address: str,
    company_tax_id: str,
) -> str:
    item_rows = []
    for index, item in enumerate(gr.items, start=1):
        item_rows.append(
            f"""
            <tr>
              <td>{index}</td>
              <td>{item.po_item.product_name}</td>
              <td>{item.po_item.sku}</td>
              <td class="right">{Decimal(item.qty_received):,.2f}</td>
              <td class="right">{Decimal(item.unit_cost):,.2f}</td>
              <td>{item.note or '-'}</td>
            </tr>
            """
        )

    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>{_css()}</style>
      </head>
      <body>
        <div class="header">
          <div class="title">ใบรับสินค้า / Goods Receipt</div>
          <p><strong>{company_name}</strong></p>
          <p>{company_address or "-"}</p>
          <p>เลขประจำตัวผู้เสียภาษี: {company_tax_id or "-"}</p>
        </div>
        <div class="grid">
          <div class="box">
            <p><strong>เลขที่ GR:</strong> {gr.gr_number}</p>
            <p><strong>เลขที่ PO:</strong> {po.po_number}</p>
            <p><strong>วันที่รับ:</strong> {gr.received_date.strftime("%d/%m/%Y")}</p>
          </div>
          <div class="box">
            <p><strong>ผู้จำหน่าย:</strong> {po.supplier.name}</p>
            <p><strong>คลัง:</strong> {gr.location.name}</p>
            <p><strong>ผู้รับสินค้า:</strong> {gr.receiver.display_name or gr.receiver.username}</p>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>ลำดับ</th>
              <th>รายการ</th>
              <th>SKU</th>
              <th class="right">จำนวนรับ</th>
              <th class="right">ราคาทุน</th>
              <th>หมายเหตุ</th>
            </tr>
          </thead>
          <tbody>
            {''.join(item_rows)}
          </tbody>
        </table>
      </body>
    </html>
    """


def html_to_pdf_or_html(html: str) -> tuple[bytes, str]:
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        return html.encode("utf-8"), "text/html"

    try:
        return HTML(string=html).write_pdf(), "application/pdf"
    except Exception:
        return html.encode("utf-8"), "text/html"


async def generate_payslip_pdf(
    item: PayrollItem,
    run: PayrollRun,
    company_name: str,
    company_address: str,
) -> tuple[bytes, str]:
    period_label = f"{MONTHS_TH[run.period_month]} {run.period_year + 543}"
    earning_lines = [line for line in item.lines if line.component_type == "earning"]
    deduction_lines = [line for line in item.lines if line.component_type == "deduction"]

    def render_lines(lines: list, placeholder: str) -> str:
        if not lines:
            return f"<tr><td colspan='2' class='muted'>{placeholder}</td></tr>"
        return "".join(
            f"<tr><td>{line.component_name}</td><td class='right'>{Decimal(line.amount):,.2f}</td></tr>"
            for line in lines
        )

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          {_css()}
          .payslip-shell {{ border: 1px solid #9ca3af; border-radius: 12px; overflow: hidden; }}
          .payslip-head {{ display:flex; justify-content:space-between; gap:20px; padding:16px 18px; background:#f8fafc; border-bottom:1px solid #d1d5db; }}
          .payslip-head h1 {{ font-size: 22px; font-weight: 700; }}
          .payslip-head .sub {{ color:#475569; }}
          .info-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 18px; padding:16px 18px; border-bottom:1px solid #d1d5db; }}
          .info-grid p {{ margin: 0 0 6px; }}
          .pay-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
          .pay-col {{ padding:0 18px 12px; }}
          .pay-col:first-child {{ border-right:1px solid #d1d5db; }}
          .pay-col table td {{ border:none; padding:6px 0; }}
          .pay-col h3 {{ font-size:15px; font-weight:700; padding:14px 0 10px; border-bottom:1px solid #d1d5db; margin-bottom:8px; }}
          .muted {{ color:#6b7280; }}
          .total-row td {{ border-top:1px solid #d1d5db; font-weight:700; padding-top:10px; }}
          .net-box {{ border-top:1px solid #d1d5db; padding:16px 18px; text-align:center; font-size:24px; font-weight:700; color:#1d4ed8; }}
          .ytd {{ border-top:1px solid #d1d5db; padding:14px 18px 18px; }}
          .ytd strong {{ display:inline-block; min-width:120px; }}
        </style>
      </head>
      <body>
        <div class="payslip-shell">
          <div class="payslip-head">
            <div>
              <h1>{company_name}</h1>
              <p class="sub">{company_address or "-"}</p>
            </div>
            <div style="text-align:right">
              <h1>สลิปเงินเดือน</h1>
              <p class="sub">Payslip</p>
            </div>
          </div>

          <div class="info-grid">
            <div>
              <p><strong>รหัสพนักงาน:</strong> {item.employee_code}</p>
              <p><strong>ชื่อ:</strong> {item.employee_name}</p>
              <p><strong>แผนก:</strong> {item.department_name or "-"}</p>
              <p><strong>ตำแหน่ง:</strong> {item.position_name or "-"}</p>
            </div>
            <div>
              <p><strong>งวด:</strong> {period_label}</p>
              <p><strong>วันจ่าย:</strong> {run.pay_date.strftime("%d/%m")}/{run.pay_date.year + 543}</p>
              <p><strong>บัญชีธนาคาร:</strong> {item.bank_account or "-"}</p>
            </div>
          </div>

          <div class="pay-grid">
            <div class="pay-col">
              <h3>รายได้</h3>
              <table>
                {render_lines(earning_lines, "ไม่มีรายการรายได้เพิ่มเติม")}
                <tr class="total-row"><td>รวมรายได้</td><td class="right">{Decimal(item.earnings_total):,.2f}</td></tr>
              </table>
            </div>
            <div class="pay-col">
              <h3>รายการหัก</h3>
              <table>
                {render_lines(deduction_lines, "ไม่มีรายการหัก")}
                <tr class="total-row"><td>รวมหัก</td><td class="right">{Decimal(item.total_deductions):,.2f}</td></tr>
              </table>
            </div>
          </div>

          <div class="net-box">เงินได้สุทธิ: ฿{Decimal(item.net_pay):,.2f}</div>

          <div class="ytd">
            <p><strong>รายได้สะสม:</strong> ฿{Decimal(item.ytd_gross):,.2f}</p>
            <p><strong>ภาษีสะสม:</strong> ฿{Decimal(item.ytd_pit):,.2f}</p>
          </div>
        </div>
      </body>
    </html>
    """
    return html_to_pdf_or_html(html)


async def generate_tax_invoice_pdf(
    doc: TaxDocument,
    items: list[TaxDocumentItem],
    company_name: str,
    company_address: str,
) -> tuple[bytes, str]:
    item_rows = []
    for item in items:
        item_rows.append(
            f"""
            <tr>
              <td>{item.line_number}</td>
              <td>{item.description}</td>
              <td class="right">{Decimal(item.qty):,.2f}</td>
              <td>{item.unit_code or "EA"}</td>
              <td class="right">{Decimal(item.unit_price):,.2f}</td>
              <td class="right">{Decimal(item.discount_amount):,.2f}</td>
              <td class="right">{Decimal(item.line_total):,.2f}</td>
              <td class="right">{Decimal(item.vat_amount):,.2f}</td>
              <td class="right">{Decimal(item.line_total) + Decimal(item.vat_amount):,.2f}</td>
            </tr>
            """
        )

    title = "ใบกำกับภาษี" if doc.document_type != "credit_note" else "ใบลดหนี้"
    buyer_name = doc.buyer_name or "-"
    buyer_tax_id = doc.buyer_tax_id or "-"
    buyer_branch_code = doc.buyer_branch_code or "-"
    buyer_address = doc.buyer_address or "-"
    seller_branch = doc.seller_branch_code or "00000"
    xml_hash_display = (doc.xml_hash or "-")[:16]

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>{_css()}</style>
      </head>
      <body>
        <div class="header">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;">
            <div>
              <div class="title">{company_name}</div>
              <p>{company_address or "-"}</p>
              <p>เลขประจำตัวผู้เสียภาษี: {doc.seller_tax_id}</p>
            </div>
            <div style="text-align:right;">
              <div class="title">{title}</div>
              <p>Tax Invoice</p>
            </div>
          </div>
        </div>

        <div class="grid">
          <div class="box">
            <p><strong>เลขที่:</strong> {doc.document_number}</p>
            <p><strong>วันที่:</strong> {format_thai_date(doc.issue_date, "long")}</p>
          </div>
          <div class="box">
            <p><strong>ประเภท:</strong> {doc.document_type}</p>
            <p><strong>อ้างอิง:</strong> {doc.reference_type} / {doc.reference_id}</p>
          </div>
        </div>

        <div class="grid">
          <div class="box">
            <p><strong>ผู้ขาย (Seller)</strong></p>
            <p>{doc.seller_name}</p>
            <p>Tax ID: {doc.seller_tax_id}</p>
            <p>สาขา: {seller_branch}</p>
            <p>{doc.seller_address or "-"}</p>
          </div>
          <div class="box">
            <p><strong>ผู้ซื้อ (Buyer)</strong></p>
            <p>{buyer_name}</p>
            <p>Tax ID: {buyer_tax_id}</p>
            <p>สาขา: {buyer_branch_code}</p>
            <p>{buyer_address}</p>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th>ลำดับ</th>
              <th>รายการ</th>
              <th class="right">จำนวน</th>
              <th>หน่วย</th>
              <th class="right">ราคา/หน่วย</th>
              <th class="right">ส่วนลด</th>
              <th class="right">ราคา</th>
              <th class="right">VAT</th>
              <th class="right">รวม</th>
            </tr>
          </thead>
          <tbody>
            {''.join(item_rows)}
          </tbody>
        </table>

        <table class="totals">
          <tr><td>ยอดรวมก่อน VAT</td><td class="right">{Decimal(doc.subtotal):,.2f}</td></tr>
          <tr><td>VAT 7%</td><td class="right">{Decimal(doc.vat_amount):,.2f}</td></tr>
          <tr><td class="grand">รวมทั้งสิ้น</td><td class="right grand">{Decimal(doc.total_amount):,.2f}</td></tr>
        </table>

        <div class="section" style="margin-top:24px;">
          <p>หมายเหตุ: เอกสารนี้ออกโดยระบบคอมพิวเตอร์</p>
          <p>XML Hash: {xml_hash_display}...</p>
        </div>
      </body>
    </html>
    """
    return html_to_pdf_or_html(html)


async def generate_wht_certificate_pdf(
    cert: WHTCertificate,
    supplier_name: str,
    supplier_tax_id: str | None,
    company_name: str,
    company_tax_id: str,
    company_address: str,
) -> tuple[bytes, str]:
    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>{_css()}</style>
      </head>
      <body>
        <div class="header">
          <div class="title">ใบรับรองการหักภาษี ณ ที่จ่าย</div>
          <p class="subtitle">หนังสือรับรองการหักภาษี ณ ที่จ่าย (50 ทวิ)</p>
        </div>
        <div class="grid">
          <div class="box">
            <p><strong>ผู้จ่ายเงิน:</strong> {company_name}</p>
            <p><strong>เลขประจำตัวผู้เสียภาษี:</strong> {company_tax_id or "-"}</p>
            <p><strong>ที่อยู่:</strong> {company_address or "-"}</p>
          </div>
          <div class="box">
            <p><strong>ผู้มีเงินได้:</strong> {supplier_name}</p>
            <p><strong>เลขประจำตัวผู้เสียภาษี:</strong> {supplier_tax_id or "-"}</p>
            <p><strong>เลขที่ใบรับรอง:</strong> {cert.certificate_number}</p>
          </div>
        </div>
        <div class="section">
          <table>
            <thead>
              <tr>
                <th>ประเภทเงินได้</th>
                <th>วันที่จ่าย</th>
                <th class="right">จำนวนเงินที่จ่าย</th>
                <th class="right">อัตราภาษี</th>
                <th class="right">ภาษีที่หัก</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{cert.wht_type}</td>
                <td>{format_thai_date(datetime.combine(cert.issue_date, datetime.min.time()), "long")}</td>
                <td class="right">{Decimal(cert.base_amount):,.2f}</td>
                <td class="right">{Decimal(cert.wht_rate):,.2f}%</td>
                <td class="right">{Decimal(cert.wht_amount):,.2f}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="box" style="margin-top:24px; min-height:88px;">
          <p><strong>ลายมือชื่อผู้จ่ายเงิน</strong></p>
          <div style="height:56px;"></div>
        </div>
      </body>
    </html>
    """
    return html_to_pdf_or_html(html)


async def generate_payment_voucher_pdf(
    payment: APPayment,
    allocations: list[APPaymentAllocationRead],
    company_name: str,
    company_address: str,
) -> tuple[bytes, str]:
    supplier_name = allocations[0].supplier_name if allocations else "-"
    rows = []
    for item in allocations:
        net_paid = q2(Decimal(item.allocated_amount) - Decimal(item.wht_amount))
        rows.append(
            f"""
            <tr>
              <td>{item.invoice_number}</td>
              <td class="right">{Decimal(item.allocated_amount):,.2f}</td>
              <td class="right">{Decimal(item.wht_amount):,.2f}</td>
              <td class="right">{net_paid:,.2f}</td>
            </tr>
            """
        )

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>{_css()}</style>
      </head>
      <body>
        <div class="header">
          <div class="title">ใบสำคัญจ่าย / Payment Voucher</div>
          <p><strong>{company_name}</strong></p>
          <p>{company_address or "-"}</p>
        </div>
        <div class="grid">
          <div class="box">
            <p><strong>เลขที่:</strong> {payment.payment_number}</p>
            <p><strong>วันที่:</strong> {format_thai_date(datetime.combine(payment.payment_date, datetime.min.time()), "long")}</p>
          </div>
          <div class="box">
            <p><strong>จ่ายให้:</strong> {supplier_name}</p>
            <p><strong>วิธีจ่าย:</strong> {payment.payment_method}</p>
            <p><strong>อ้างอิง:</strong> {payment.reference_no or "-"}</p>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>เลขที่ใบแจ้งหนี้</th>
              <th class="right">จำนวน</th>
              <th class="right">WHT</th>
              <th class="right">จ่ายสุทธิ</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
        <table class="totals">
          <tr><td>รวมจ่าย</td><td class="right">{Decimal(payment.total_amount):,.2f}</td></tr>
        </table>
        <div class="signatures">
          <div class="signature-box">ผู้จ่าย</div>
          <div class="signature-box">ผู้อนุมัติ</div>
          <div class="signature-box">ผู้รับเงิน</div>
        </div>
      </body>
    </html>
    """
    return html_to_pdf_or_html(html)


async def generate_po_pdf(
    po: PurchaseOrder,
    company_name: str,
    company_address: str,
    company_tax_id: str,
) -> bytes:
    html = render_po_html(po, company_name, company_address, company_tax_id)
    content, media_type = html_to_pdf_or_html(html)
    if media_type != "application/pdf":
        raise ValueError("WeasyPrint unavailable")
    return content


async def generate_gr_pdf(
    gr: GoodsReceipt,
    po: PurchaseOrder,
    company_name: str,
    company_address: str,
    company_tax_id: str,
) -> bytes:
    html = render_gr_html(gr, po, company_name, company_address, company_tax_id)
    content, media_type = html_to_pdf_or_html(html)
    if media_type != "application/pdf":
        raise ValueError("WeasyPrint unavailable")
    return content


async def generate_count_sheet_pdf(
    session: StockCountSession,
    items: list[StockCountItem],
    branch_name: str,
    location_name: str,
    company_name: str,
) -> tuple[bytes, str]:
    item_rows = []
    for index, item in enumerate(items, start=1):
        item_rows.append(
            f"""
            <tr>
              <td>{index}</td>
              <td>{item.sku}</td>
              <td>{item.product_name}</td>
              <td>{item.unit_code or "-"}</td>
              <td class="right">{Decimal(item.expected_qty):,.4f}</td>
              <td style="height: 34px;"></td>
              <td>{item.note or ""}</td>
            </tr>
            """
        )

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>{_css()}</style>
      </head>
      <body>
        <div class="header">
          <div class="title">ใบนับสินค้า / Stock Count Sheet</div>
          <p><strong>{company_name}</strong></p>
        </div>

        <div class="grid">
          <div class="box">
            <p><strong>เลขที่ Session:</strong> {session.session_number}</p>
            <p><strong>สาขา:</strong> {branch_name}</p>
            <p><strong>คลัง:</strong> {location_name}</p>
          </div>
          <div class="box">
            <p><strong>วันที่นับ:</strong> {format_thai_date(session.started_at or session.created_at, "long") if session.started_at else format_thai_date(datetime.combine(session.count_date, datetime.min.time()), "long")}</p>
            <p><strong>สถานะ:</strong> {session.status}</p>
            <p><strong>ช่องลายเซ็นผู้ตรวจนับ:</strong> ____________________</p>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th>ลำดับ</th>
              <th>SKU</th>
              <th>ชื่อสินค้า</th>
              <th>หน่วย</th>
              <th class="right">จำนวนตาม system</th>
              <th>จำนวนนับจริง</th>
              <th>หมายเหตุ</th>
            </tr>
          </thead>
          <tbody>
            {''.join(item_rows)}
          </tbody>
        </table>

        <div class="signatures">
          <div class="signature-box">ผู้ตรวจนับ</div>
          <div class="signature-box">ผู้ตรวจสอบ</div>
          <div class="signature-box">วันที่</div>
        </div>
      </body>
    </html>
    """
    return html_to_pdf_or_html(html)


async def generate_variance_report_pdf(report: VarianceReport) -> tuple[bytes, str]:
    variance_rows = []
    for item in report.variances:
        row_color = "#fef2f2" if item.variance_qty < 0 else "#ecfdf5"
        variance_rows.append(
            f"""
            <tr style="background:{row_color};">
              <td>{item.product_name}<br /><span style="color:#6b7280;font-size:11px;">{item.sku}</span></td>
              <td class="right">{Decimal(item.expected_qty):,.4f}</td>
              <td class="right">{Decimal(item.actual_qty):,.4f}</td>
              <td class="right">{Decimal(item.variance_qty):,.4f}</td>
              <td class="right">{Decimal(item.variance_value):,.2f}</td>
              <td class="right">{Decimal(item.variance_pct):,.2f}%</td>
            </tr>
            """
        )

    matched_rows = []
    for item in report.matched_items:
        matched_rows.append(
            f"""
            <tr>
              <td>{item.product_name}<br /><span style="color:#6b7280;font-size:11px;">{item.sku}</span></td>
              <td class="right">{Decimal(item.actual_qty):,.4f} (ตรงกัน ✓)</td>
            </tr>
            """
        )

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>{_css()}</style>
      </head>
      <body>
        <div class="header">
          <div class="title">รายงานผลการนับสินค้า / Stock Count Variance Report</div>
          <p><strong>Session:</strong> {report.session_number}</p>
          <p><strong>คลัง:</strong> {report.location_name} | <strong>สาขา:</strong> {report.branch_name}</p>
          <p><strong>วันที่:</strong> {report.count_date_thai} | <strong>ผู้ปิด session:</strong> {report.completed_by_name}</p>
        </div>

        <div class="grid">
          <div class="box"><strong>ตรง</strong><br />{report.items_matched} รายการ</div>
          <div class="box"><strong>เกิน</strong><br />{report.items_over} รายการ</div>
          <div class="box"><strong>ขาด</strong><br />{report.items_short} รายการ</div>
          <div class="box"><strong>มูลค่าผลต่าง</strong><br />{Decimal(report.total_variance_value):,.2f} บาท</div>
        </div>

        <div class="section">
          <h3 style="margin-bottom:8px;">รายการที่มีผลต่าง</h3>
          <table>
            <thead>
              <tr>
                <th>สินค้า</th>
                <th class="right">คาดไว้</th>
                <th class="right">นับจริง</th>
                <th class="right">ผลต่าง</th>
                <th class="right">มูลค่าผลต่าง</th>
                <th class="right">%</th>
              </tr>
            </thead>
            <tbody>
              {''.join(variance_rows) or '<tr><td colspan="6" style="text-align:center;">ไม่พบผลต่าง</td></tr>'}
            </tbody>
          </table>
        </div>

        <div class="section">
          <h3 style="margin-bottom:8px;">สินค้าที่ตรงกัน</h3>
          <table>
            <thead>
              <tr>
                <th>สินค้า</th>
                <th class="right">จำนวน</th>
              </tr>
            </thead>
            <tbody>
              {''.join(matched_rows) or '<tr><td colspan="2" style="text-align:center;">ไม่มีรายการ</td></tr>'}
            </tbody>
          </table>
        </div>

        <p style="margin-top:16px;"><strong>{getattr(report, 'adjustment_note', 'ตรวจสอบสถานะการปรับสต็อกในระบบ')}</strong></p>
      </body>
    </html>
    """
    return html_to_pdf_or_html(html)


async def generate_shipping_label_pdf(
    shipment: Shipment,
    carrier_name: str,
) -> tuple[bytes, str]:
    cod_line = (
        f"<div class='meta-strong cod'>COD: ฿{Decimal(shipment.cod_amount or 0):,.2f}</div>"
        if shipment.is_cod
        else ""
    )
    dimensions = " × ".join(str(value) for value in [shipment.width_cm, shipment.height_cm, shipment.depth_cm] if value is not None) or "-"
    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@400;500;700;800&display=swap');
          @page {{ size: 100mm 150mm; margin: 6mm; }}
          body {{ font-family: 'Sarabun', sans-serif; color: #111827; font-size: 12px; margin: 0; }}
          .label {{ border: 2px solid #111827; border-radius: 14px; overflow: hidden; background: #fff; }}
          .section {{ padding: 10px 12px; border-bottom: 1px solid #111827; }}
          .section:last-child {{ border-bottom: none; }}
          .carrier {{ background: #f3f4f6; }}
          .carrier-name {{ font-size: 22px; font-weight: 800; letter-spacing: 0.04em; }}
          .heading {{ font-size: 11px; font-weight: 700; text-transform: uppercase; color: #4b5563; margin-bottom: 4px; }}
          .recipient-name {{ font-size: 18px; font-weight: 800; line-height: 1.2; }}
          .recipient-phone {{ font-size: 20px; font-weight: 800; line-height: 1.2; margin-top: 2px; }}
          .address {{ white-space: pre-wrap; line-height: 1.45; }}
          .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }}
          .meta-strong {{ font-weight: 700; }}
          .tracking {{ font-size: 18px; font-weight: 800; letter-spacing: 0.06em; margin-bottom: 4px; }}
          .barcode-placeholder {{ border: 1px dashed #6b7280; padding: 8px; text-align: center; font-size: 11px; letter-spacing: 0.2em; margin-top: 8px; }}
          .cod {{ color: #b91c1c; }}
          .footer-note {{ color: #6b7280; font-size: 10px; margin-top: 6px; }}
        </style>
      </head>
      <body>
        <div class="label">
          <div class="section carrier">
            <div class="heading">Carrier</div>
            <div class="carrier-name">{carrier_name}</div>
          </div>

          <div class="section">
            <div class="heading">ผู้ส่ง</div>
            <div class="meta-strong">{shipment.sender_name}</div>
            <div>{shipment.sender_phone}</div>
            <div class="address">{shipment.sender_address}</div>
          </div>

          <div class="section">
            <div class="heading">ผู้รับ</div>
            <div class="recipient-name">{shipment.recipient_name}</div>
            <div class="recipient-phone">{shipment.recipient_phone}</div>
            <div class="address">{shipment.recipient_address}</div>
          </div>

          <div class="section">
            <div class="heading">เลขพัสดุ</div>
            <div class="tracking">{shipment.tracking_number or "-"}</div>
            <div class="barcode-placeholder">BARCODE: {shipment.tracking_number or shipment.shipment_number}</div>
            <div class="meta-grid" style="margin-top: 10px;">
              <div><span class="meta-strong">น้ำหนัก:</span> {shipment.weight_grams}g</div>
              <div><span class="meta-strong">ขนาด:</span> {dimensions}</div>
              <div><span class="meta-strong">เลขที่:</span> {shipment.shipment_number}</div>
              <div><span class="meta-strong">บริการ:</span> {shipment.service_name or "-"}</div>
            </div>
            {cod_line}
            <div class="footer-note">A4 fallback will be used automatically if PDF rendering is unavailable.</div>
          </div>
        </div>
      </body>
    </html>
    """
    return html_to_pdf_or_html(html)
