import api from "./api";

export const etaxApi = {
  listDocuments: (params?: {
    document_type?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    limit?: number;
  }) => api.get("/etax/documents", { params }),

  getDocument: (id: string) => api.get(`/etax/documents/${id}`),

  issueTaxInvoice: (data: {
    sale_order_id: string;
    document_type: string;
    buyer_tax_id?: string;
    buyer_name?: string;
    buyer_branch_code?: string;
    buyer_address?: string;
  }) => api.post("/etax/documents/tax-invoice", data),

  issueCreditNote: (data: { original_document_id: string; reason: string }) =>
    api.post("/etax/documents/credit-note", data),

  downloadXml: (id: string) => api.get(`/etax/documents/${id}/xml`, { responseType: "blob" }),

  downloadPdf: (id: string) => api.get(`/etax/documents/${id}/pdf`, { responseType: "blob" }),

  cancelDocument: (id: string, reason: string) =>
    api.post(`/etax/documents/${id}/cancel`, { cancel_reason: reason }),

  vatSummary: (year: number, month: number) =>
    api.get("/etax/vat-summary", { params: { year, month } }),
};
