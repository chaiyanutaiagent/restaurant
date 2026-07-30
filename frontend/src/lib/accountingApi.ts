import type { ApiResponse } from "@/types/api";
import type { Account, JournalEntry, ProfitLossReport, TrialBalanceReport } from "@/types/accounting";
import api from "./api";

export const accountingApi = {
  listAccounts: (params?: { account_type?: string; tree?: boolean }) =>
    api.get<ApiResponse<Account[]>>("/accounting/accounts", { params }),
  createAccount: (data: object) => api.post<ApiResponse<Account>>("/accounting/accounts", data),
  updateAccount: (id: string, data: object) =>
    api.patch<ApiResponse<Account>>(`/accounting/accounts/${id}`, data),
  getAccountLedger: (id: string, params: { period_year: number; period_month: number }) =>
    api.get<ApiResponse<object>>(`/accounting/accounts/${id}/ledger`, { params }),
  listEntries: (params?: object) =>
    api.get<ApiResponse<JournalEntry[]>>("/accounting/entries", { params }),
  getEntry: (id: string) => api.get<ApiResponse<JournalEntry>>(`/accounting/entries/${id}`),
  createEntry: (data: object) => api.post<ApiResponse<JournalEntry>>("/accounting/entries", data),
  reverseEntry: (id: string) => api.post<ApiResponse<JournalEntry>>(`/accounting/entries/${id}/reverse`),
  trialBalance: (periodYear: number, periodMonth: number) =>
    api.get<ApiResponse<TrialBalanceReport>>("/accounting/reports/trial-balance", {
      params: { period_year: periodYear, period_month: periodMonth }
    }),
  profitLoss: (periodYear: number, periodMonth: number, cumulative = false) =>
    api.get<ApiResponse<ProfitLossReport>>("/accounting/reports/profit-loss", {
      params: { period_year: periodYear, period_month: periodMonth, cumulative }
    })
};
