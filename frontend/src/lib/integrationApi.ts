import api from "./api";

export const integrationApi = {
  listApiKeys: () => api.get("/integrations/api-keys"),
  createApiKey: (data: { name: string; purpose: string; owner_contact: string; scopes: string[]; expires_at: string }) =>
    api.post("/integrations/api-keys", data),
  revokeApiKey: (id: string) => api.post(`/integrations/api-keys/${id}/revoke`),
  rotateApiKey: (id: string, data: { reason: string; expires_at: string }) => api.post(`/integrations/api-keys/${id}/rotate`, data),

  listWebhooks: () => api.get("/integrations/webhooks"),
  createWebhook: (data: object) => api.post("/integrations/webhooks", data),
  updateWebhook: (id: string, data: object) => api.patch(`/integrations/webhooks/${id}`, data),
  deleteWebhook: (id: string) => api.delete(`/integrations/webhooks/${id}`),
  getDeliveries: (id: string) => api.get(`/integrations/webhooks/${id}/deliveries`),
  testWebhook: (id: string) => api.post(`/integrations/webhooks/${id}/test`),
  rotateWebhookSecret: (id: string, data: { secret: string; reason: string }) => api.post(`/integrations/webhooks/${id}/rotate-secret`, data),
  retryDelivery: (id: string) => api.post(`/integrations/webhook-deliveries/${id}/retry`),

  listExternalOrders: (params?: { status?: string; source?: string; page?: number; limit?: number }) =>
    api.get("/integrations/external-orders", { params }),
  reviewExternalOrder: (id: string, decision: "accept" | "reject", reason: string) =>
    api.post(`/integrations/external-orders/${id}/review`, { decision, reason }),
  fulfillExternalOrder: (id: string) => api.post(`/integrations/external-orders/${id}/fulfill`)
};
