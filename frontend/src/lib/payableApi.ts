import api from "./api";

export const payableApi = {
  listInvoices: (params?: {
    supplier_id?: string;
    status?: string;
    overdue_only?: boolean;
    date_from?: string;
    date_to?: string;
    page?: number;
    limit?: number;
  }) => api.get("/payable/invoices", { params }),
  createInvoice: (data: object) => api.post("/payable/invoices", data),
  getInvoice: (id: string) => api.get(`/payable/invoices/${id}`),
  cancelInvoice: (id: string) => api.post(`/payable/invoices/${id}/cancel`),
  listPayments: (params?: { page?: number; limit?: number }) => api.get("/payable/payments", { params }),
  createPayment: (data: object) => api.post("/payable/payments", data),
  getPayment: (id: string) => api.get(`/payable/payments/${id}`),
  downloadVoucher: (id: string) => api.get(`/payable/payments/${id}/voucher`, { responseType: "blob" }),
  listWhtCerts: (params?: { supplier_id?: string; page?: number; limit?: number }) =>
    api.get("/payable/wht-certificates", { params }),
  getWhtCert: (id: string) => api.get(`/payable/wht-certificates/${id}`),
  downloadWhtCert: (id: string) => api.get(`/payable/wht-certificates/${id}/pdf`, { responseType: "blob" }),
  vatReturn: (year: number, month: number) => api.get("/payable/vat-return", { params: { year, month } })
};
