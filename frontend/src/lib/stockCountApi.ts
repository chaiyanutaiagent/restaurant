import api from "./api";

export const stockCountApi = {
  listSessions: (params?: {
    branch_id?: string;
    location_id?: string;
    status?: string;
    page?: number;
    limit?: number;
  }) => api.get("/stock-count/sessions", { params }),

  createSession: (data: {
    branch_id: string;
    location_id: string;
    count_date?: string;
    note?: string;
    product_ids?: string[];
  }) => api.post("/stock-count/sessions", data),

  getSession: (id: string) => api.get(`/stock-count/sessions/${id}`),

  startSession: (id: string) => api.post(`/stock-count/sessions/${id}/start`),

  updateItem: (sessionId: string, itemId: string, data: { actual_qty: number; note?: string }) =>
    api.patch(`/stock-count/sessions/${sessionId}/items/${itemId}`, data),

  batchUpdateItems: (sessionId: string, items: Array<{ item_id: string; actual_qty: number; note?: string }>) =>
    api.post(`/stock-count/sessions/${sessionId}/items/batch`, { items }),

  completeSession: (id: string, data: { apply_adjustments: boolean; note?: string }) =>
    api.post(`/stock-count/sessions/${id}/complete`, data),

  cancelSession: (id: string) => api.post(`/stock-count/sessions/${id}/cancel`),

  getVarianceReport: (id: string) => api.get(`/stock-count/sessions/${id}/variance-report`),

  downloadSheet: (id: string) => api.get(`/stock-count/sessions/${id}/sheet`, { responseType: "blob" }),

  downloadVariancePdf: (id: string) =>
    api.get(`/stock-count/sessions/${id}/variance-report/pdf`, { responseType: "blob" })
};
