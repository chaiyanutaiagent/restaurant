import axios from "axios";
import type { ApiResponse } from "@/types/api";
import type { StorefrontBranch, StorefrontProduct, StorefrontSummary } from "@/types/storefront";

const storefrontApiClient = axios.create({ baseURL: "/api/public/storefront" });

export const storefrontApi = {
  summary: (businessSlug?: string) => storefrontApiClient.get<ApiResponse<StorefrontSummary>>(
    businessSlug ? `/businesses/${encodeURIComponent(businessSlug)}` : ""
  ),
  products: (params?: { search?: string; category_id?: string; in_stock_only?: boolean; page?: number; limit?: number }, businessSlug?: string) =>
    storefrontApiClient.get<ApiResponse<StorefrontProduct[]>>(
      businessSlug ? `/businesses/${encodeURIComponent(businessSlug)}/products` : "/products",
      { params }
    ),
  branches: (params?: { active_only?: boolean }, businessSlug?: string) =>
    storefrontApiClient.get<ApiResponse<StorefrontBranch[]>>(
      businessSlug ? `/businesses/${encodeURIComponent(businessSlug)}/branches` : "/branches",
      { params }
    ),
};
