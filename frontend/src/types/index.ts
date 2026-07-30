export type ApiHealthResponse = {
  status: string;
  version: string;
};

export type OfflineQueueItem = {
  id?: number;
  type: string;
  payload: string;
  createdAt: string;
  syncedAt?: string;
};

export * from "@/types/product";
export * from "@/types/stock";
export * from "@/types/pos";
export * from "@/types/report";
export * from "@/types/purchase";
export * from "@/types/transfer";
export * from "@/types/accounting";
export * from "@/types/etax";
export * from "@/types/hr";
export * from "@/types/integration";
export * from "@/types/logistics";
export * from "@/types/paymentGateway";
