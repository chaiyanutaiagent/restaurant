import api from "@/lib/api";
import type { Supplier } from "@/types/purchase";

export const supplierApi = {
  list: (params?: { search?: string; is_active?: boolean; page?: number; limit?: number }) =>
    api.get("/purchase/suppliers", { params }),
  get: (id: string) => api.get(`/purchase/suppliers/${id}`),
  create: (data: Partial<Supplier>) => api.post("/purchase/suppliers", data),
  update: (id: string, data: Partial<Supplier>) => api.patch(`/purchase/suppliers/${id}`, data),
  delete: (id: string) => api.delete(`/purchase/suppliers/${id}`)
};

export const poApi = {
  list: (params?: object) => api.get("/purchase/orders", { params }),
  get: (id: string) => api.get(`/purchase/orders/${id}`),
  create: (data: object) => api.post("/purchase/orders", data),
  update: (id: string, data: object) => api.patch(`/purchase/orders/${id}`, data),
  submit: (id: string) => api.post(`/purchase/orders/${id}/submit`),
  approve: (id: string, note?: string) => api.post(`/purchase/orders/${id}/approve`, { note }),
  cancel: (id: string, reason: string) => api.post(`/purchase/orders/${id}/cancel`, { reason }),
  pdf: (id: string) => api.get(`/purchase/orders/${id}/pdf`, { responseType: "blob" })
};

export const grApi = {
  create: (data: object) => api.post("/purchase/receipts", data),
  listByPO: (poId: string) => api.get("/purchase/receipts", { params: { po_id: poId } }),
  get: (id: string) => api.get(`/purchase/receipts/${id}`),
  pdf: (id: string) => api.get(`/purchase/receipts/${id}/pdf`, { responseType: "blob" })
};
