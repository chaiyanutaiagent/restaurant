import api from "./api";

export const logisticsApi = {
  listCarriers: () => api.get("/logistics/carriers"),

  estimate: (data: { weight_grams: number; zone?: string; is_cod?: boolean }) =>
    api.post("/logistics/estimate", data),

  listShipments: (params?: {
    status?: string;
    carrier_id?: string;
    search?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    limit?: number;
  }) => api.get("/logistics/shipments", { params }),

  createShipment: (data: object) => api.post("/logistics/shipments", data),

  getShipment: (id: string) => api.get(`/logistics/shipments/${id}`),

  updateShipment: (id: string, data: object) => api.patch(`/logistics/shipments/${id}`, data),

  updateStatus: (id: string, data: { status: string; location?: string; note?: string }) =>
    api.post(`/logistics/shipments/${id}/status`, data),

  downloadLabel: (id: string) => api.get(`/logistics/shipments/${id}/label`, { responseType: "blob" })
};
