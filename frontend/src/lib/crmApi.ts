import api from "./api";

export const crmApi = {
  getSettings: () => api.get("/crm/settings"),
  updateSettings: (data: object) => api.patch("/crm/settings", data),
  listTiers: () => api.get("/crm/tiers"),
  listTags: () => api.get("/crm/tags"),
  createTag: (data: object) => api.post("/crm/tags", data),

  searchCustomers: (q: string, limit = 10) =>
    api.get("/crm/customers/search", { params: { q, limit } }),
  listCustomers: (params?: {
    tier_id?: string;
    tag_id?: string;
    is_active?: boolean;
    search?: string;
    page?: number;
    limit?: number;
  }) => api.get("/crm/customers", { params }),
  getCustomer: (id: string) => api.get(`/crm/customers/${id}`),
  createCustomer: (data: object) => api.post("/crm/customers", data),
  updateCustomer: (id: string, data: object) => api.patch(`/crm/customers/${id}`, data),
  getPurchaseHistory: (id: string) => api.get(`/crm/customers/${id}/history`),
  getPointsHistory: (id: string, params?: { page?: number; limit?: number }) =>
    api.get(`/crm/customers/${id}/points`, { params }),

  earnPoints: (data: object) => api.post("/crm/points/earn", data),
  redeemPoints: (data: object) => api.post("/crm/points/redeem", data),
  adjustPoints: (data: object) => api.post("/crm/points/adjust", data),
};
