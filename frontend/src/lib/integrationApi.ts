import api from "./api";

export const integrationApi = {
  listApiKeys: () => api.get("/integrations/api-keys"),
  createApiKey: (data: { name: string; scopes: string[]; expires_at?: string }) =>
    api.post("/integrations/api-keys", data),
  revokeApiKey: (id: string) => api.post(`/integrations/api-keys/${id}/revoke`),

  listWebhooks: () => api.get("/integrations/webhooks"),
  createWebhook: (data: object) => api.post("/integrations/webhooks", data),
  updateWebhook: (id: string, data: object) => api.patch(`/integrations/webhooks/${id}`, data),
  deleteWebhook: (id: string) => api.delete(`/integrations/webhooks/${id}`),
  getDeliveries: (id: string) => api.get(`/integrations/webhooks/${id}/deliveries`),
  testWebhook: (id: string) => api.post(`/integrations/webhooks/${id}/test`),

  listExternalOrders: (params?: { status?: string; source?: string; page?: number; limit?: number }) =>
    api.get("/integrations/external-orders", { params }),
  fulfillExternalOrder: (id: string) => api.post(`/integrations/external-orders/${id}/fulfill`)
};
