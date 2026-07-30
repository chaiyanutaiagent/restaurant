import axios from "axios";
import type { ApiResponse } from "@/types/api";
import type { StorefrontBranch, StorefrontProduct, StorefrontSummary } from "@/types/storefront";

const storefrontApiClient = axios.create({ baseURL: "/api/public/storefront" });

export const storefrontApi = {
  summary: () => storefrontApiClient.get<ApiResponse<StorefrontSummary>>(""),
  products: (params?: { search?: string; category_id?: string; in_stock_only?: boolean; page?: number; limit?: number }) =>
    storefrontApiClient.get<ApiResponse<StorefrontProduct[]>>("/products", { params }),
  branches: (params?: { active_only?: boolean }) =>
    storefrontApiClient.get<ApiResponse<StorefrontBranch[]>>("/branches", { params }),
};
