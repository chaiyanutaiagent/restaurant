import type { ApiResponse } from "@/types/api";
import type {
  BranchAssignableRole,
  BranchDetail,
  BranchReplacementRule,
  BranchSettings,
  InviteResponse,
  RoleDetail,
  UserAccessApprovalResult,
  UserAccessRequest,
  UserAccessRequestStatus,
  UserDetail
} from "@/types/admin";
import api from "./api";

export const userApi = {
  list: (params?: {
    branch_id?: string;
    is_active?: boolean;
    search?: string;
    page?: number;
    limit?: number;
  }) => api.get<ApiResponse<UserDetail[]>>("/system/users", { params }),
  get: (id: string) => api.get<ApiResponse<UserDetail>>(`/system/users/${id}`),
  create: (data: object) => api.post<ApiResponse<UserDetail>>("/system/users", data),
  update: (id: string, data: object) => api.patch<ApiResponse<UserDetail>>(`/system/users/${id}`, data),
  deactivate: (id: string) => api.post<ApiResponse<UserDetail>>(`/system/users/${id}/deactivate`),
  changePassword: (id: string, newPassword: string) =>
    api.post<ApiResponse<{ message: string }>>(`/system/users/${id}/change-password`, {
      new_password: newPassword
    }),
  assignBranch: (id: string, data: { branch_id: string; role_id: string; is_default?: boolean }) =>
    api.post<ApiResponse<UserDetail>>(`/system/users/${id}/branches`, data),
  removeBranch: (userId: string, branchId: string) =>
    api.delete(`/system/users/${userId}/branches/${branchId}`)
};

export const roleApi = {
  list: () => api.get<ApiResponse<RoleDetail[]>>("/system/roles"),
  create: (data: {
    name: string;
    description?: string;
    permission_ids: string[];
    is_branch_assignable?: boolean;
  }) =>
    api.post<ApiResponse<RoleDetail>>("/system/roles", data),
  update: (id: string, data: object) => api.patch<ApiResponse<RoleDetail>>(`/system/roles/${id}`, data),
  delete: (id: string) => api.delete(`/system/roles/${id}`)
};

export const branchApi = {
  list: () => api.get<ApiResponse<BranchDetail[]>>("/system/branches"),
  get: (id: string) => api.get<ApiResponse<BranchDetail>>(`/system/branches/${id}`),
  create: (data: object) => api.post<ApiResponse<BranchDetail>>("/system/branches", data),
  update: (id: string, data: object) => api.patch<ApiResponse<BranchDetail>>(`/system/branches/${id}`, data),
  getSettings: (id: string) => api.get<ApiResponse<BranchSettings>>(`/system/branches/${id}/settings`),
  updateSettings: (id: string, data: object) =>
    api.patch<ApiResponse<BranchSettings>>(`/system/branches/${id}/settings`, data),
  listReplacementRules: (id: string) =>
    api.get<ApiResponse<BranchReplacementRule[]>>(`/system/branches/${id}/replacement-rules`),
  upsertReplacementRule: (id: string, data: { source_product_id: string; replacement_product_id: string }) =>
    api.post<ApiResponse<BranchReplacementRule>>(`/system/branches/${id}/replacement-rules`, data),
  deleteReplacementRule: (id: string, sourceProductId: string) =>
    api.delete(`/system/branches/${id}/replacement-rules/${sourceProductId}`)
};

export const invitationApi = {
  create: (data: object) => api.post<ApiResponse<InviteResponse>>("/system/invitations", data),
  accept: (
    data: { invitation_id?: string; otp_code: string; username: string; password: string },
    companyId: string
  ) =>
    api.post<ApiResponse<{ message: string }>>("/system/invitations/accept", data, {
      headers: { "X-Company-ID": companyId }
    })
};

type UserAccessRequestFilters = {
  brand_slug?: string;
  branch_id?: string;
  status?: UserAccessRequestStatus | "";
  search?: string;
  page?: number;
  limit?: number;
};

export const userAccessApi = {
  assignableRoles: () =>
    api.get<ApiResponse<BranchAssignableRole[]>>("/system/branch-assignable-roles"),
  list: (params?: UserAccessRequestFilters) =>
    api.get<ApiResponse<UserAccessRequest[]>>("/system/user-access-requests", { params }),
  mine: (params: Omit<UserAccessRequestFilters, "branch_id"> & { brand_slug: string }) =>
    api.get<ApiResponse<UserAccessRequest[]>>("/system/user-access-requests/mine", { params }),
  get: (id: string) =>
    api.get<ApiResponse<UserAccessRequest>>(`/system/user-access-requests/${id}`),
  create: (data: {
    brand_slug: string;
    requested_role_id: string;
    username: string;
    password: string;
    employee_id?: string | null;
    employee_code?: string | null;
    first_name: string;
    last_name: string;
    email?: string | null;
    phone?: string | null;
    request_note?: string | null;
  }) => api.post<ApiResponse<UserAccessRequest>>("/system/user-access-requests", data),
  approve: (id: string, data: { approved_role_id: string; review_note?: string | null }) =>
    api.post<ApiResponse<UserAccessApprovalResult>>(`/system/user-access-requests/${id}/approve`, data),
  reject: (id: string, reason: string) =>
    api.post<ApiResponse<UserAccessRequest>>(`/system/user-access-requests/${id}/reject`, { reason }),
  cancel: (id: string, brandSlug: string, reason?: string) =>
    api.post<ApiResponse<UserAccessRequest>>(`/system/user-access-requests/${id}/cancel`, {
      brand_slug: brandSlug,
      reason
    }),
  resend: (id: string) =>
    api.post<ApiResponse<UserAccessApprovalResult>>(
      `/system/user-access-requests/${id}/resend-invitation`
    )
};
