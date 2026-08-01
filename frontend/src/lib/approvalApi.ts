import axios from "axios";
import api from "@/lib/api";
import type { ApiResponse } from "@/types/api";
import type {
  ApprovalSession,
  ApprovalSessionRequest,
  ManagerPinStatus
} from "@/types/approval";

export const approvalApi = {
  getManagerPinStatus: () =>
    api.get<ApiResponse<ManagerPinStatus>>("/approvals/manager-pin"),
  setManagerPin: (data: { current_password: string; pin: string }) =>
    api.put<ApiResponse<ManagerPinStatus>>("/approvals/manager-pin", data),
  createSession: (data: ApprovalSessionRequest) =>
    api.post<ApiResponse<ApprovalSession>>("/approvals/sessions", data)
};

export function compactApprovalPayload(
  value: Record<string, unknown>
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, item]) => {
      if (item === null || item === undefined) return [];
      if (Array.isArray(item)) {
        return [[key, item.map((entry) => {
          if (entry && typeof entry === "object" && !Array.isArray(entry)) {
            return compactApprovalPayload(entry as Record<string, unknown>);
          }
          return entry;
        })]];
      }
      if (typeof item === "object") {
        return [[key, compactApprovalPayload(item as Record<string, unknown>)]];
      }
      return [[key, item]];
    })
  );
}

export function approvalErrorDetail(error: unknown): {
  code?: string;
  message?: string;
} | null {
  if (!axios.isAxiosError(error)) return null;
  const responseData = error.response?.data as { detail?: unknown } | undefined;
  const detail = responseData?.detail;
  if (!detail || typeof detail !== "object") return null;
  return detail as { code?: string; message?: string };
}

export function errorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const responseData = error.response?.data as { detail?: unknown } | undefined;
    const detail = responseData?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
  }
  return error instanceof Error ? error.message : fallback;
}
