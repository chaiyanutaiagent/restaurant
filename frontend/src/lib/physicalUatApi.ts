import api from "@/lib/api";
import type { ApiResponse } from "@/types/api";

export type PhysicalUATResult = "pending" | "pass" | "fail" | "na";
export type PhysicalUATCheck = {
  id: string;
  check_key: string;
  category: string;
  label: string;
  source: "automatic" | "manual";
  required: boolean;
  result: PhysicalUATResult;
  reason: string | null;
  evidence_reference: string | null;
  defect_id: string | null;
  defect_severity: string | null;
  tested_by: string | null;
  tested_at: string | null;
  evidence: Record<string, unknown>;
};
export type PhysicalUATSession = {
  id: string;
  company_id: string;
  branch_id: string;
  device_id: string;
  release_commit: string;
  environment: "uat";
  status: "in_progress" | "not_ready" | "ready_for_signoff" | "uat_approved";
  created_by: string;
  submitted_by: string | null;
  submitted_at: string | null;
  technical_approved_by: string | null;
  technical_approved_at: string | null;
  business_approved_by: string | null;
  business_approved_at: string | null;
  device_snapshot: Record<string, unknown>;
  environment_snapshot: Record<string, unknown>;
  summary: Record<string, number>;
  checks: PhysicalUATCheck[];
  created_at: string;
  updated_at: string;
};

export const physicalUatApi = {
  list: () => api.get<ApiResponse<PhysicalUATSession[]>>("/uat/device-readiness"),
  get: (id: string) => api.get<ApiResponse<PhysicalUATSession>>(`/uat/device-readiness/${id}`),
  create: (data: {
    device_id: string;
    release_commit: string;
    device_model: string;
    os_version: string;
    browser_version: string;
    printer_model_connection?: string | null;
    network_profile: string;
  }) => api.post<ApiResponse<PhysicalUATSession>>("/uat/device-readiness", data),
  updateCheck: (sessionId: string, checkKey: string, data: {
    result: "pass" | "fail" | "na";
    reason?: string | null;
    evidence_reference?: string | null;
    defect_id?: string | null;
    defect_severity?: "P0" | "P1" | "P2" | "P3" | null;
    evidence?: Record<string, unknown>;
  }) => api.put<ApiResponse<PhysicalUATSession>>(`/uat/device-readiness/${sessionId}/checks/${checkKey}`, data),
  submit: (sessionId: string) => api.post<ApiResponse<PhysicalUATSession>>(`/uat/device-readiness/${sessionId}/submit`),
  signoff: (sessionId: string, role: "technical" | "business", note: string) =>
    api.post<ApiResponse<PhysicalUATSession>>(`/uat/device-readiness/${sessionId}/signoff`, { role, note }),
};
