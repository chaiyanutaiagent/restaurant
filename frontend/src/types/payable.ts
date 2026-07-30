export type InvoiceStatus = "unpaid" | "partial" | "paid" | "cancelled";
export type PaymentMethod = "bank_transfer" | "cheque" | "cash";

export interface SupplierInvoice {
  id: string;
  invoice_number: string;
  supplier_id: string;
  supplier_name: string;
  po_id: string | null;
  supplier_ref: string | null;
  status: InvoiceStatus;
  invoice_date: string;
  due_date: string;
  subtotal: number;
  vat_amount: number;
  wht_amount: number;
  total_amount: number;
  paid_amount: number;
  remaining_amount: number;
  note: string | null;
  is_overdue: boolean;
  created_at: string;
}

export interface APPaymentAllocation {
  id: string;
  payment_id: string;
  invoice_id: string;
  allocated_amount: number;
  wht_amount: number;
  wht_rate: number;
  wht_type: string | null;
  invoice_number: string;
  supplier_name: string;
}

export interface APPayment {
  id: string;
  payment_number: string;
  payment_date: string;
  payment_method: PaymentMethod;
  bank_account: string | null;
  reference_no: string | null;
  total_amount: number;
  note: string | null;
  created_at: string;
  allocations: APPaymentAllocation[];
}

export interface WHTCertificate {
  id: string;
  certificate_number: string;
  payment_id: string;
  supplier_id: string;
  supplier_name: string;
  supplier_tax_id: string | null;
  issue_date: string;
  wht_type: string;
  wht_rate: number;
  base_amount: number;
  wht_amount: number;
  income_type: string | null;
  created_at: string;
}

export interface VatReturnReport {
  year: number;
  month: number;
  month_label: string;
  output_vat_sales: number;
  output_vat_total: number;
  input_vat_purchases: number;
  input_vat_total: number;
  net_vat_payable: number;
  net_vat_label: string;
  output_doc_count: number;
  input_invoice_count: number;
  filing_due_date: string;
}
