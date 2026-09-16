export type VatType = "included" | "excluded" | "exempt";
export type TaxCategory = "standard" | "zero" | "exempt";
export type VatFilingMode = "separate" | "consolidated";

export interface CompanyTaxProfile {
  id: string | null;
  configured: boolean;
  company_id: string;
  legal_name: string;
  tax_id: string | null;
  vat_registered: boolean;
  vat_registration_date: string | null;
  registered_address: string | null;
  default_price_vat_type: VatType;
  default_vat_rate: string | number;
  vat_filing_mode: VatFilingMode;
  consolidated_filing_approved: boolean;
  updated_at: string | null;
}

export interface BranchTaxProfile {
  id: string | null;
  configured: boolean;
  company_id: string;
  branch_id: string;
  branch_code: string;
  branch_name: string;
  tax_branch_code: string | null;
  is_head_office: boolean;
  legal_name: string | null;
  registered_address: string | null;
  vat_registration_date: string | null;
  filing_enabled: boolean;
  effective_from: string | null;
  effective_to: string | null;
  updated_at: string | null;
}

export interface TaxRateRule {
  id: string;
  company_id: string;
  code: string;
  name: string;
  tax_category: TaxCategory;
  rate: string | number;
  price_vat_type: VatType;
  effective_from: string;
  effective_to: string | null;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TaxSettings {
  company: CompanyTaxProfile;
  branches: BranchTaxProfile[];
  rates: TaxRateRule[];
}

export interface CompanyTaxProfilePayload {
  legal_name: string;
  tax_id: string | null;
  vat_registered: boolean;
  vat_registration_date: string | null;
  registered_address: string | null;
  default_price_vat_type: VatType;
  default_vat_rate: number;
  vat_filing_mode: VatFilingMode;
  consolidated_filing_approved: boolean;
  effective_from: string;
  reason: string;
}
export interface BranchTaxProfilePayload {
  tax_branch_code: string;
  is_head_office: boolean;
  legal_name: string | null;
  registered_address: string | null;
  vat_registration_date: string | null;
  filing_enabled: boolean;
  effective_from: string;
  effective_to: string | null;
  reason: string;
}

export interface TaxRateRuleCreatePayload {
  code: string;
  name: string;
  tax_category: TaxCategory;
  rate: number;
  price_vat_type: VatType;
  effective_from: string;
  effective_to: string | null;
  is_default: boolean;
  reason: string;
}
