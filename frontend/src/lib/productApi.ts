import api from "@/lib/api";
import type { Category, PriceList, Product, Unit } from "@/types/product";

export const categoryApi = {
  list: (tree = false) => api.get(`/categories?tree=${tree}`),
  create: (data: Partial<Category>) => api.post("/categories", data),
  update: (id: string, data: Partial<Category>) => api.patch(`/categories/${id}`, data),
  delete: (id: string) => api.delete(`/categories/${id}`),
  uploadImage: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post(`/categories/${id}/image`, form);
  }
};

export const unitApi = {
  list: () => api.get("/units"),
  create: (data: Partial<Unit>) => api.post("/units", data),
  update: (id: string, data: Partial<Unit>) => api.patch(`/units/${id}`, data),
  delete: (id: string) => api.delete(`/units/${id}`)
};

export const productApi = {
  list: (params?: {
    page?: number;
    limit?: number;
    search?: string;
    category_id?: string;
    is_active?: boolean;
  }) => api.get("/products", { params }),
  get: (id: string) => api.get(`/products/${id}`),
  create: (data: Partial<Product>) => api.post("/products", data),
  update: (id: string, data: Partial<Product>) => api.patch(`/products/${id}`, data),
  delete: (id: string) => api.delete(`/products/${id}`),
  uploadImage: (id: string, file: File, isPrimary = true) => {
    const form = new FormData();
    form.append("file", file);
    form.append("is_primary", String(isPrimary));
    return api.post(`/products/${id}/image`, form);
  },
  deleteImage: (productId: string, imageId: string) => api.delete(`/products/${productId}/images/${imageId}`),
  setPrimaryImage: (productId: string, imageId: string) =>
    api.patch(`/products/${productId}/images/${imageId}/primary`),
  addVariant: (productId: string, data: object) => api.post(`/products/${productId}/variants`, data),
  updateVariant: (productId: string, variantId: string, data: object) =>
    api.patch(`/products/${productId}/variants/${variantId}`, data),
  deleteVariant: (productId: string, variantId: string) =>
    api.delete(`/products/${productId}/variants/${variantId}`),
  getPrice: (productId: string, params?: { price_list_id?: string; variant_id?: string; qty?: number }) =>
    api.get(`/products/${productId}/price`, { params })
};

export const priceListApi = {
  list: () => api.get("/price-lists"),
  create: (data: Partial<PriceList>) => api.post("/price-lists", data),
  setPrice: (priceListId: string, data: object) => api.post(`/price-lists/${priceListId}/items`, data)
};
