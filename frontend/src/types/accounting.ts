export type AccountType = "asset" | "liability" | "equity" | "revenue" | "expense";
export type NormalBalance = "debit" | "credit";

export interface Account {
  id: string;
  company_id: string;
  parent_id: string | null;
  code: string;
  name: string;
  name_en: string | null;
  account_type: AccountType;
  account_subtype: string | null;
  normal_balance: NormalBalance;
  is_header: boolean;
  is_active: boolean;
  is_system: boolean;
  description: string | null;
  sort_order: number;
  children: Account[];
}

export interface JournalLine {
  id: string;
  entry_id: string;
  account_id: string;
  line_number: number;
  description: string | null;
  debit_amount: number;
  credit_amount: number;
  account_code: string;
  account_name: string;
}

export interface JournalEntry {
  id: string;
  entry_number: string;
  entry_date: string;
  period_year: number;
  period_month: number;
  entry_type: string;
  reference_type: string | null;
  reference_id: string | null;
  description: string;
  is_posted: boolean;
  is_reversed: boolean;
  created_by: string;
  created_at: string;
  posted_at: string | null;
  lines: JournalLine[];
  total_debit: number;
}

export interface TrialBalanceRow {
  account_code: string;
  account_name: string;
  account_type: string;
  debit_balance: number;
  credit_balance: number;
}

export interface TrialBalanceReport {
  period_year: number;
  period_month: number;
  period_label: string;
  rows: TrialBalanceRow[];
  total_debit: number;
  total_credit: number;
  is_balanced: boolean;
}

export interface ProfitLossReport {
  period_year: number;
  period_month: number;
  period_label: string;
  total_revenue: number;
  total_cogs: number;
  gross_profit: number;
  gross_margin_pct: number;
  total_operating_expense: number;
  net_profit: number;
  net_margin_pct: number;
  revenue_rows: TrialBalanceRow[];
  cogs_rows: TrialBalanceRow[];
  expense_rows: TrialBalanceRow[];
}
