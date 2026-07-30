import api from "@/lib/api";

export const transferApi = {
  list: (params?: {
    from_branch_id?: string;
    to_branch_id?: string;
    status?: string;
    page?: number;
    limit?: number;
  }) => api.get("/transfer/orders", { params }),

  get: (id: string) => api.get(`/transfer/orders/${id}`),

  create: (data: object) => api.post("/transfer/orders", data),

  submit: (id: string) => api.post(`/transfer/orders/${id}/submit`),

  approve: (id: string, data: { items: object[]; note?: string }) =>
    api.post(`/transfer/orders/${id}/approve`, data),

  ship: (id: string, note?: string) => api.post(`/transfer/orders/${id}/ship`, { note }),

  receive: (id: string, data: { items: object[]; note?: string }) =>
    api.post(`/transfer/orders/${id}/receive`, data),

  cancel: (id: string, reason: string) => api.post(`/transfer/orders/${id}/cancel`, { reason }),

  multiBranchStock: () => api.get("/transfer/stock/multi-branch")
};
