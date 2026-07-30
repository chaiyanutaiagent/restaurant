import api from "./api";

export const gatewayApi = {
  getConfig: () => api.get("/payments/config"),
  updateConfig: (data: object) => api.patch("/payments/config", data),
  testLineNotify: (data?: { message?: string }) => api.post("/payments/config/test-line", data ?? {}),
  testEmail: (data?: { recipient?: string }) => api.post("/payments/config/test-email", data ?? {}),

  listSessions: (params?: { status?: string; gateway?: string; page?: number }) =>
    api.get("/payments/sessions", { params }),
  createPromptPay: (data: { amount: number; branch_id: string; reference_type?: string; reference_id?: string }) =>
    api.post("/payments/sessions/promptpay", data),
  createOmise: (data: object) => api.post("/payments/sessions/omise", data),
  getSession: (id: string) => api.get(`/payments/sessions/${id}`),
  checkSession: (id: string) => api.post(`/payments/sessions/${id}/check`),
  confirmSession: (id: string) => api.post(`/payments/sessions/${id}/confirm`),

  listNotifications: (params?: { page?: number; limit?: number }) =>
    api.get("/payments/notifications", { params }),
};
