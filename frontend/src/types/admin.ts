import type { Permission } from "@/types/user";

export type RoleScope = "company" | "brand" | "branch" | "station";

export interface UserBranchDetail {
  branch_id: string;
  branch_name: string;
  branch_code: string;
  brand_id: string | null;
  business_type: "restaurant" | "retail_pos" | "takeaway" | null;
  target_database: "restaurant" | "retail_pos" | "takeaway" | null;
  role_id: string;
  role_name: string;
  is_default: boolean;
}

export interface UserDetail {
  id: string;
  company_id: string;
  username: string;
  email: string | null;
  phone: string | null;
  first_name: string | null;
  last_name: string | null;
  display_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  last_login_at: string | null;
  created_at: string;
  branches: UserBranchDetail[];
}

export interface RoleDetail {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  is_branch_assignable: boolean;
  allowed_scope_types: RoleScope[];
  created_at: string;
  permissions: Permission[];
  user_count: number;
}

export interface RolePreset {
  key: string;
  name: string;
  description: string;
  default_scope: RoleScope;
  allowed_scopes: RoleScope[];
  is_branch_assignable: boolean;
  permission_ids: string[];
  permission_codes: string[];
  missing_permission_codes: string[];
  is_available: boolean;
  policy_version: string;
}

export interface StaffRoleAssignment {
  id: string;
  company_id: string;
  user_id: string;
  role_id: string;
  role_name: string;
  scope_type: RoleScope;
  scope_key: string;
  scope_label: string;
  brand_id: string | null;
  brand_name: string | null;
  branch_id: string | null;
  branch_name: string | null;
  station_key: string | null;
  assignment_reason: string;
  assigned_by: string;
  assigned_at: string;
  revoked_by: string | null;
  revoked_at: string | null;
  revocation_reason: string | null;
}

export interface StaffAssignmentOptions {
  company: { id: string; name: string };
  brands: Array<{ id: string; name: string; business_type: string }>;
  branches: Array<{
    id: string;
    code: string;
    name: string;
    brand_id: string;
    stations: string[];
  }>;
}

export interface BranchSettings {
  id: string;
  branch_id: string;
  pos_receipt_header: string | null;
  pos_receipt_footer: string | null;
  pos_require_customer: boolean;
  pos_allow_discount: boolean;
  pos_max_discount_pct: number;
  pos_cashier_discount_limit_pct: number;
  pos_price_override_auto_limit_pct: number;
  pos_price_override_auto_limit_amount: number;
  pos_price_override_max_deviation_pct: number;
  pos_price_override_min_margin_pct: number;
  pos_price_override_self_approval: boolean;
  pos_hold_draft_ttl_minutes: number;
  pos_cash_movement_approval_threshold: number;
  pos_shift_variance_soft_threshold: number;
  pos_shift_variance_approval_threshold: number;
  stock_adjust_approval_threshold_qty: number;
  promptpay_target: string | null;
  promptpay_name: string | null;
  promptpay_qr_url: string | null;
  working_hours: Record<string, { open: string; close: string }> | null;
  public_storefront_enabled: boolean;
  allow_negative_stock: boolean;
  low_stock_alert_enabled: boolean;
  receipt_show_tax_id: boolean;
  receipt_show_logo: boolean;
  receipt_logo_url: string | null;
  receipt_copies: number;
  notify_low_stock_email: string | null;
  // F&B Module
  fb_enabled: boolean;
  fb_service_mode: "dine_in" | "quick_service" | "both";
  fb_table_qr_enabled: boolean;
  fb_bill_at_table: boolean;
  fb_queue_enabled: boolean;
  fb_queue_reset: "daily" | "per_shift";
  fb_queue_prefix: string;
  fb_pickup_display_enabled: boolean;
  fb_line_notify_token: string | null;
  fb_line_mode: "group" | "individual";
  fb_kitchen_stations: string[] | null;
  fb_setup_completed: boolean;
  fb_qs_qr_token: string | null;
}

export interface BranchDetail {
  id: string;
  company_id: string;
  brand_id: string | null;
  business_type: "restaurant" | "retail_pos" | "takeaway" | null;
  target_database: "restaurant" | "retail_pos" | "takeaway" | null;
  code: string;
  name: string;
  name_en: string | null;
  address: string | null;
  landmark: string | null;
  phone: string | null;
  email: string | null;
  latitude: number | null;
  longitude: number | null;
  google_maps_url: string | null;
  is_warehouse: boolean;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  user_count: number;
  settings: BranchSettings | null;
}

export interface BranchReplacementRule {
  id: string;
  branch_id: string;
  source_product_id: string;
  source_product_name: string;
  replacement_product_id: string;
  replacement_product_name: string;
  created_at: string;
}

export interface InviteResponse {
  invitation_id: string;
  otp_code: string;
  expires_at: string;
  message: string;
}

export type UserAccessRequestStatus =
  | "pending"
  | "approved"
  | "activated"
  | "rejected"
  | "cancelled";

export interface BranchAssignableRole {
  id: string;
  name: string;
  description: string | null;
}

export interface UserAccessRequest {
  id: string;
  company_id: string;
  brand_id: string | null;
  brand_slug: string | null;
  brand_name: string | null;
  branch_id: string;
  branch_code: string;
  branch_name: string;
  requested_role_id: string;
  requested_role_name: string;
  approved_role_id: string | null;
  approved_role_name: string | null;
  employee_id: string | null;
  employee_code: string | null;
  requested_username: string | null;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  request_note: string | null;
  status: UserAccessRequestStatus;
  requested_by: string;
  requester_name: string;
  requested_at: string;
  reviewed_by: string | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  activated_user_id: string | null;
  activated_username: string | null;
  activated_at: string | null;
  invitation_id: string | null;
  invitation_expires_at: string | null;
  invitation_used_at: string | null;
  invitation_revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserAccessApprovalResult {
  request: UserAccessRequest;
  activation_mode: "activated" | "invitation";
  created_username: string | null;
  invitation_id: string | null;
  company_id: string;
  otp_code: string | null;
  expires_at: string | null;
}
