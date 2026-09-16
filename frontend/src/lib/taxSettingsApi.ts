import api from "./api";
import type { ApiResponse } from "@/types/api";
import type {
  BranchTaxProfile,
  BranchTaxProfilePayload,
  CompanyTaxProfile,
  CompanyTaxProfilePayload,
  TaxRateRule,
  TaxRateRuleCreatePayload,
  TaxSettings,
} from "@/types/taxSettings";

export const taxSettingsApi = {
  get: () => api.get<ApiResponse<TaxSettings>>("/tax-settings"),
  updateCompany: (data: CompanyTaxProfilePayload) =>
    api.put<ApiResponse<CompanyTaxProfile>>("/tax-settings/company", data),
  updateBranch: (branchId: string, data: BranchTaxProfilePayload) =>
    api.put<ApiResponse<BranchTaxProfile>>(`/tax-settings/branches/${branchId}`, data),
  createRate: (data: TaxRateRuleCreatePayload) =>
    api.post<ApiResponse<TaxRateRule>>("/tax-settings/rates", data),
  updateRate: (
    ruleId: string,
    data: Partial<Omit<TaxRateRuleCreatePayload, "code">> & { is_active?: boolean; reason: string },
  ) => api.patch<ApiResponse<TaxRateRule>>(`/tax-settings/rates/${ruleId}`, data),
};
