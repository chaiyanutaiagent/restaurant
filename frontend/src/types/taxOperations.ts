export type TaxSummary = {
  output_base: string;
  output_tax: string;
  input_base: string;
  input_tax: string;
  net_tax: string;
  wht_amount: string;
};

export type TaxLedgerRow = {
  id: string;
  source_module: string;
  tax_direction: "output" | "input";
  tax_category: string;
  document_number: string;
  document_date: string;
  counterparty_name: string | null;
  counterparty_tax_id: string | null;
  base_amount: string;
  tax_amount: string;
  total_amount: string;
  vat_rate: string;
  status: string;
  reconciliation_status: string;
};

export type TaxIssue = {
  id: string;
  issue_code: string;
  severity: "warning" | "error" | "blocker";
  status: "open" | "resolved" | "ignored";
  message: string;
  source_document_type: string | null;
  source_document_id: string | null;
  resolution_note: string | null;
};

export type TaxWhtRow = {
  id: string;
  certificate_number: string;
  issue_date: string;
  supplier_name: string;
  supplier_tax_id: string | null;
  tax_entity_type: string;
  wht_type: string;
  base_amount: string;
  wht_amount: string;
};

export type TaxExportRow = {
  id: string;
  export_type: string;
  status: string;
  filename: string;
  row_count: number;
  base_amount: string;
  tax_amount: string;
  content_sha256: string;
  generated_at: string;
};

export type TaxOperationsDashboard = {
  year: number;
  month: number;
  branch_id: string | null;
  summary: TaxSummary;
  period: { id: string | null; status: string; ledger_sha256: string | null; reviewed_at?: string | null; closed_at?: string | null; reopened_at?: string | null; reopen_reason?: string | null };
  ledger: TaxLedgerRow[];
  issues: TaxIssue[];
  wht: TaxWhtRow[];
  exports: TaxExportRow[];
  readiness: { ready_to_close: boolean; open_blockers: number; open_warnings: number; pending_reconciliation: number; configured: boolean };
};

export type TaxExportType = "vat_sales" | "vat_purchases" | "pp30_summary" | "wht_pnd3" | "wht_pnd53" | "etax_manifest" | "tax_archive";
