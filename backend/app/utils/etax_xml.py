from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import hashlib
import xml.etree.ElementTree as ET

from app.models.etax import TaxDocument, TaxDocumentItem

TWOPLACES = Decimal("0.01")
NAMESPACE = "urn:etda:th:taxinvoice:1.0"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("", NAMESPACE)
ET.register_namespace("xsi", XSI_NAMESPACE)


def q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _format_amount(value: Decimal | int | float | str | None) -> str:
    return f"{q2(value):.2f}"


def _root() -> ET.Element:
    return ET.Element(
        ET.QName(NAMESPACE, "TaxInvoice"),
        {ET.QName(XSI_NAMESPACE, "schemaLocation"): "urn:etda:th:taxinvoice:1.0 taxinvoice.xsd"},
    )


def _append_common_document(root: ET.Element, doc: TaxDocument) -> None:
    ET.SubElement(root, ET.QName(NAMESPACE, "DocumentType")).text = doc.document_type
    ET.SubElement(root, ET.QName(NAMESPACE, "DocumentID")).text = doc.document_number
    ET.SubElement(root, ET.QName(NAMESPACE, "IssueDate")).text = doc.issue_date.isoformat()
    ET.SubElement(root, ET.QName(NAMESPACE, "IssueTime")).text = doc.issue_datetime.strftime("%H:%M:%S")

    seller_party = ET.SubElement(root, ET.QName(NAMESPACE, "SellerParty"))
    ET.SubElement(seller_party, ET.QName(NAMESPACE, "TaxID"), {"schemeID": "TXID"}).text = doc.seller_tax_id
    ET.SubElement(seller_party, ET.QName(NAMESPACE, "BranchID")).text = doc.seller_branch_code or "00000"
    ET.SubElement(seller_party, ET.QName(NAMESPACE, "Name")).text = doc.seller_name
    ET.SubElement(seller_party, ET.QName(NAMESPACE, "Address")).text = doc.seller_address or "-"

    if doc.buyer_tax_id or doc.buyer_name or doc.buyer_address:
        buyer_party = ET.SubElement(root, ET.QName(NAMESPACE, "BuyerParty"))
        if doc.buyer_tax_id:
            ET.SubElement(buyer_party, ET.QName(NAMESPACE, "TaxID"), {"schemeID": "TXID"}).text = doc.buyer_tax_id
        if doc.buyer_branch_code:
            ET.SubElement(buyer_party, ET.QName(NAMESPACE, "BranchID")).text = doc.buyer_branch_code
        ET.SubElement(buyer_party, ET.QName(NAMESPACE, "Name")).text = doc.buyer_name or "-"
        ET.SubElement(buyer_party, ET.QName(NAMESPACE, "Address")).text = doc.buyer_address or "-"


def _append_items(root: ET.Element, items: list[TaxDocumentItem], sign: int = 1) -> None:
    lines_node = ET.SubElement(root, ET.QName(NAMESPACE, "LineItems"))
    for item in items:
        line = ET.SubElement(lines_node, ET.QName(NAMESPACE, "LineItem"), {"lineNumber": str(item.line_number)})
        ET.SubElement(line, ET.QName(NAMESPACE, "Description")).text = item.description
        ET.SubElement(line, ET.QName(NAMESPACE, "Quantity"), {"unitCode": item.unit_code or "EA"}).text = _format_amount(
            Decimal(item.qty) * sign
        )
        ET.SubElement(line, ET.QName(NAMESPACE, "UnitPrice")).text = _format_amount(item.unit_price)
        ET.SubElement(line, ET.QName(NAMESPACE, "Discount")).text = _format_amount(item.discount_amount)
        ET.SubElement(line, ET.QName(NAMESPACE, "VATRate")).text = _format_amount(item.vat_rate)
        ET.SubElement(line, ET.QName(NAMESPACE, "VATAmount")).text = _format_amount(Decimal(item.vat_amount) * sign)
        ET.SubElement(line, ET.QName(NAMESPACE, "LineTotal")).text = _format_amount(Decimal(item.line_total) * sign)


def _append_totals(root: ET.Element, doc: TaxDocument, sign: int = 1) -> None:
    totals = ET.SubElement(root, ET.QName(NAMESPACE, "Totals"))
    ET.SubElement(totals, ET.QName(NAMESPACE, "SubTotal")).text = _format_amount(Decimal(doc.subtotal) * sign)
    ET.SubElement(totals, ET.QName(NAMESPACE, "Discount")).text = _format_amount(Decimal(doc.discount_amount) * sign)
    ET.SubElement(totals, ET.QName(NAMESPACE, "VATAmount")).text = _format_amount(Decimal(doc.vat_amount) * sign)
    ET.SubElement(totals, ET.QName(NAMESPACE, "TotalAmount")).text = _format_amount(Decimal(doc.total_amount) * sign)


def _serialize(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def generate_tax_invoice_xml(
    doc: TaxDocument,
    items: list[TaxDocumentItem],
) -> str:
    root = _root()
    _append_common_document(root, doc)
    _append_items(root, items)
    _append_totals(root, doc)
    ET.SubElement(root, ET.QName(NAMESPACE, "DocumentHash"), {"algorithm": "SHA256"}).text = "PENDING"
    return _serialize(root)


def generate_credit_note_xml(
    doc: TaxDocument,
    items: list[TaxDocumentItem],
    original_doc: TaxDocument,
) -> str:
    root = _root()
    _append_common_document(root, doc)
    ET.SubElement(root, ET.QName(NAMESPACE, "OriginalDocumentID")).text = original_doc.document_number
    ET.SubElement(root, ET.QName(NAMESPACE, "Reason")).text = doc.reason or "-"
    _append_items(root, items, sign=-1)
    _append_totals(root, doc, sign=-1)
    ET.SubElement(root, ET.QName(NAMESPACE, "DocumentHash"), {"algorithm": "SHA256"}).text = "PENDING"
    return _serialize(root)


def compute_xml_hash(xml_content: str) -> str:
    return hashlib.sha256(xml_content.encode("utf-8")).hexdigest()
