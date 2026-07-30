export interface ApiResponse<T> {
  data: T;
  meta: { version: string; page?: number; limit?: number; total?: number };
  error: string | null;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}
