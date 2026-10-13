"""Read-only business document templates. Amounts come from stored transactions.

These are not tax invoices, immutable snapshots, or evidence of a completed payment.
Keep this module independent of ORM and network resources for deterministic printing.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from html import escape

TEMPLATE_VERSION = "business-documents-1"

CSS = """
@page { size: A4; margin: 15mm 13mm 18mm;
  @top-right { content: string(document-number); font-size: 8pt; color: #64748b; }
  @bottom-left { content: "Foodchainservice · business-documents-1"; font-size: 8pt; color: #64748b; }
  @bottom-right { content: "หน้า " counter(page) " / " counter(pages); font-size: 8pt; }
}
body { font-family: 'Noto Sans Thai', 'Sarabun', 'Thonburi', sans-serif;
  color: #172b3a; font-size: 10pt; line-height: 1.55; }
h1 { font-size: 21pt; margin: 0; } p { margin: 2pt 0; }
.header { border-bottom: 3pt solid #0f766e; padding-bottom: 9pt; margin-bottom: 12pt; }
.muted, small { color: #526578; font-size: 8pt; }
.meta { margin: 10pt 0 14pt; } .meta td { background: #f1f5f9; }
.document-number { string-set: document-number content(); }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
th, td { padding: 6pt; border-bottom: 1px solid #d5dee5; vertical-align: top;
  overflow-wrap: anywhere; word-wrap: break-word; }
th { background: #e6f2f0; text-align: left; font-size: 9pt; }
thead { display: table-header-group; } tr { break-inside: avoid; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.summary { width: 65%; margin: 12pt 0 0 auto; break-inside: avoid; }
.summary td:first-child { width: 72%; }
.grand { font-weight: bold; border-top: 2px solid #0f766e; }
.notice { margin-top: 12pt; font-size: 8pt; color: #526578; }
.signatures { margin-top: 35pt; break-inside: avoid; }
.signatures td { text-align: center; border: 0; }
.signature-line { border-top: 1px solid #64748b; margin: 0 12pt 6pt; }
.status { font-weight: bold; } .note { white-space: pre-wrap; }
"""


def text(value: object) -> str:
    return escape(str(value if value is not None and value != "" else "-"), quote=True)


def amount(value: object) -> Decimal:
    return Decimal(str(value if value is not None else 0))


def money(value: object) -> str:
    return f"{amount(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def quantity(value: object) -> str:
    return f"{amount(value):,.4f}".rstrip("0").rstrip(".")


def day(value: date | datetime | None) -> str:
    return f"{value.day:02d}/{value.month:02d}/{value.year + 543}" if value else "-"


def fields(pairs: list[tuple[str, object]]) -> str:
    return "".join(f"<p><strong>{text(label)}:</strong> {text(value)}</p>" for label, value in pairs)


def status_label(value: object) -> str:
    return {"draft": "ฉบับร่าง", "approved": "อนุมัติแล้ว", "cancelled": "ยกเลิก",
            "pending": "รอดำเนินการ", "posted": "ผ่านรายการแล้ว", "paid": "ชำระแล้ว",
            "completed": "เสร็จสิ้น", "partial": "รับบางส่วน", "received": "รับครบแล้ว"}.get(str(value), str(value or "-"))


def document(title: str, number: str, company_name: str, company_address: str,
             company_tax_id: str, left: list, right: list, table: str,
             summary: list[tuple[str, object]], signers: tuple[str, str, str], note: str | None = None) -> str:
    totals = "".join(f'<tr class="{"grand" if i == len(summary) - 1 else ""}"><td>{text(label)}</td>'
                     f'<td class="num">{money(value)}</td></tr>' for i, (label, value) in enumerate(summary))
    signatures = "".join(f'<td><div class="signature-line"></div>{text(signer)}<p>วันที่ ____/____/____</p></td>' for signer in signers)
    return f'''<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="template-version" content="{TEMPLATE_VERSION}"><title>{text(title)} {text(number)}</title>
<style>{CSS}</style></head><body>
<div class="header"><h1>{text(title)}</h1><p><strong>{text(company_name)}</strong></p>
<p class="note">{text(company_address)}</p><p>เลขประจำตัวผู้เสียภาษี {text(company_tax_id)}</p>
<p class="muted document-number">เลขที่ {text(number)} · สกุลเงิน THB (บาท)</p></div>
<table class="meta"><tr><td>{fields(left)}</td><td>{fields(right)}</td></tr></table>
{table}<table class="summary">{totals}</table>
{f'<p class="note notice">หมายเหตุ: {text(note)}</p>' if note else ''}
<p class="notice">เอกสารอ้างอิงรายการในระบบ ไม่ใช่ใบกำกับภาษีหรือหนังสือรับรองหัก ณ ที่จ่าย
ยอดเงินตามข้อมูลที่บันทึกไว้ การพิมพ์ไม่สร้างธุรกรรมใหม่</p>
<table class="signatures"><tr>{signatures}</tr></table></body></html>'''


def render_po_html(po, company_name: str, company_address: str, company_tax_id: str) -> str:
    rows = []
    for index, item in enumerate(po.items, 1):
        vat_label = {"included": "รวม VAT", "excluded": "แยก VAT", "exempt": "ยกเว้น VAT"}.get(item.vat_type, item.vat_type)
        vat_caption = text(vat_label) if item.vat_type == "exempt" else f"{text(vat_label)} {quantity(item.vat_rate)}%"
        # Only presentation of stored components, never recalculate tax at today's rate.
        line_total = amount(item.subtotal) + (amount(item.vat_amount) if item.vat_type == "excluded" else 0)
        rows.append(f'''<tr><td>{index}</td><td>{text(item.product_name)}<br><small>{text(item.sku)}<br>
{vat_caption}</small></td>
<td class="num">{quantity(item.qty_ordered)}<br><small>{text(item.unit_code)}</small></td>
<td class="num">{money(item.unit_cost)}</td><td class="num">{money(item.discount_amount)}</td>
<td class="num">{money(item.vat_amount)}</td><td class="num">{money(line_total)}</td></tr>''')
    table = '''<table><colgroup><col style="width:5%"><col style="width:29%"><col style="width:11%">
<col style="width:14%"><col style="width:12%"><col style="width:13%"><col style="width:16%"></colgroup>
<thead><tr><th>#</th><th>รายการ / รหัส</th><th class="num">จำนวน</th><th class="num">ราคา/หน่วย</th>
<th class="num">ส่วนลด</th><th class="num">VAT</th><th class="num">รวม VAT</th></tr></thead><tbody>''' + ''.join(rows) + '</tbody></table>'
    return document("ใบสั่งซื้อ / Purchase Order", po.po_number, company_name, company_address, company_tax_id,
                    [("เลขที่ PO", po.po_number), ("วันที่สั่งซื้อ", day(po.order_date)),
                     ("กำหนดรับ", day(po.expected_date)), ("สถานะ", status_label(po.status))],
                    [("ผู้จำหน่าย", po.supplier.name), ("เลขผู้เสียภาษี", po.supplier.tax_id),
                     ("เงื่อนไขชำระ", f"{po.supplier.payment_term_days} วัน")], table,
                    [("ส่วนลดรวม (แสดงประกอบ ไม่หักซ้ำ)", po.discount_amount),
                     ("VAT รวมตามรายการ", po.vat_amount), ("หัก ณ ที่จ่ายตาม PO", po.wht_amount),
                     ("ยอดสุทธิตามใบสั่งซื้อ", po.total_amount)],
                    ("ผู้สั่งซื้อ", "ผู้อนุมัติ", "ผู้จำหน่าย"), getattr(po, "note", None))


def render_gr_html(gr, po, company_name: str, company_address: str, company_tax_id: str) -> str:
    rows = ''.join(f'''<tr><td>{i}</td><td>{text(item.po_item.product_name)}<br><small>{text(item.po_item.sku)}</small></td>
<td class="num">{quantity(item.qty_received)}<br><small>{text(item.po_item.unit_code)}</small></td>
<td class="num">{money(item.unit_cost)}</td><td>{text(item.note)}</td></tr>''' for i, item in enumerate(gr.items, 1))
    table = '''<table><colgroup><col style="width:6%"><col style="width:35%"><col style="width:16%">
<col style="width:18%"><col style="width:25%"></colgroup><thead><tr><th>#</th><th>รายการ / รหัส</th>
<th class="num">จำนวนรับ</th><th class="num">ทุน/หน่วย</th><th>หมายเหตุ</th></tr></thead><tbody>''' + rows + '</tbody></table>'
    return document("ใบรับสินค้า / Goods Receipt", gr.gr_number, company_name, company_address, company_tax_id,
                    [("เลขที่ GR", gr.gr_number), ("อ้างอิง PO", po.po_number), ("วันที่รับ", day(gr.received_date))],
                    [("ผู้จำหน่าย", po.supplier.name), ("คลัง", gr.location.name),
                     ("ผู้รับสินค้า", gr.receiver.display_name or gr.receiver.username)], table, [],
                    ("ผู้ส่งสินค้า", "ผู้รับสินค้า", "ผู้ตรวจสอบ"), getattr(gr, "note", None))


def render_payment_voucher_html(payment, allocations, company_name: str, company_address: str,
                                company_tax_id: str = "") -> str:
    rows = ''.join(f'''<tr><td>{text(item.invoice_number)}</td><td>{text(item.supplier_name)}</td>
<td class="num">{money(item.allocated_amount)}</td><td class="num">{money(item.wht_amount)}</td>
<td class="num">{money(amount(item.allocated_amount) - amount(item.wht_amount))}</td></tr>''' for item in allocations)
    table = '''<table><colgroup><col style="width:23%"><col style="width:26%"><col style="width:17%">
<col style="width:17%"><col style="width:17%"></colgroup><thead><tr><th>ใบแจ้งหนี้</th><th>จ่ายให้</th>
<th class="num">ยอดชำระหนี้</th><th class="num">หัก ณ ที่จ่าย</th><th class="num">จ่ายสุทธิ</th></tr></thead><tbody>''' + rows + '</tbody></table>'
    methods = {"cash": "เงินสด", "transfer": "โอนเงิน", "bank_transfer": "โอนเงิน", "cheque": "เช็ค"}
    return document("ใบสำคัญจ่าย / Payment Voucher", payment.payment_number, company_name, company_address, company_tax_id,
                    [("เลขที่", payment.payment_number), ("วันที่จ่าย", day(payment.payment_date))],
                    [("วิธีจ่าย", methods.get(payment.payment_method, payment.payment_method)),
                     ("อ้างอิง", payment.reference_no)], table,
                    [("หัก ณ ที่จ่ายรวม", sum((amount(a.wht_amount) for a in allocations), Decimal(0))),
                     ("รวมจ่ายตามใบสำคัญ", payment.total_amount)], ("ผู้จ่าย", "ผู้อนุมัติ", "ผู้รับเงิน"),
                    getattr(payment, "note", None))
