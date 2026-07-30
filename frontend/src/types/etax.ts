export type TaxDocumentType =
  "full_tax_invoice" | "abbreviated_tax_invoice" | "credit_note" | "debit_note";
export type TaxDocumentStatus = "issued" | "cancelled" | "amended";

export interface TaxDocumentItem {
  id: string;
  document_id: string;
  line_number: number;
  description: string;
  unit_code: string | null;
  qty: number;
  unit_price: number;
  discount_amount: number;
  vat_type: string;
  vat_rate: number;
  vat_amount: number;
  line_total: number;
}

export interface TaxDocument {
  id: string;
  document_number: string;
  document_type: TaxDocumentType;
  status: TaxDocumentStatus;
  branch_id: string;
  reference_type: string;
  reference_id: string;
  seller_tax_id: string;
  seller_name: string;
  seller_branch_code: string | null;
  seller_address: string | null;
  buyer_tax_id: string | null;
  buyer_name: string | null;
  buyer_branch_code: string | null;
  buyer_address: string | null;
  subtotal: number;
  discount_amount: number;
  vat_rate: number;
  vat_amount: number;
  total_amount: number;
  issue_date: string;
  issue_datetime: string;
  original_document_id: string | null;
  reason: string | null;
  xml_hash: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  created_at: string;
  items: TaxDocumentItem[];
}

export interface TaxDocumentListItem {
  id: string;
  document_number: string;
  document_type: TaxDocumentType;
  status: TaxDocumentStatus;
  buyer_name: string | null;
  buyer_tax_id: string | null;
  total_amount: number;
  vat_amount: number;
  issue_date: string;
  created_at: string;
}

export interface VatSummary {
  year: number;
  month: number;
  output_vat: number;
  input_vat: number;
  net_vat_payable: number;
  document_count: number;
  total_sales: number;
}
