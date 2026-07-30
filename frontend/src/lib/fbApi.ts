import api from "@/lib/api";
import type { ApiResponse } from "@/types/api";
import type { BranchSettings } from "@/types/admin";

export type FBSetupPayload = {
  has_tables: boolean;
  table_zones: Array<{
    zone_name: string;
    table_count: number;
    table_name_prefix: string;
    table_capacity: number;
  }>;
  table_qr_enabled: boolean;
  bill_at_table: boolean;
  queue_reset: "daily" | "per_shift";
  queue_prefix: string;
  pickup_display_enabled: boolean;
  kitchen_stations: string[];
};

export type FBSetupResult = {
  settings: BranchSettings;
  tables_ready: number;
  tables_created: string[];
};

export type FBSettingsPayload = {
  has_tables?: boolean;
  table_qr_enabled?: boolean;
  bill_at_table?: boolean;
  queue_reset?: "daily" | "per_shift";
  queue_prefix?: string;
  pickup_display_enabled?: boolean;
  line_notify_token?: string | null;
  kitchen_stations?: string[];
};

export const fbApi = {
  settings: () =>
    api.get<ApiResponse<BranchSettings>>("/restaurant/settings"),
  updateSettings: (payload: FBSettingsPayload) =>
    api.patch<ApiResponse<BranchSettings>>("/restaurant/settings", payload),
  setup: (payload: FBSetupPayload) =>
    api.post<ApiResponse<FBSetupResult>>("/restaurant/setup", payload),
};
