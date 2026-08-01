export type ApprovalAction =
  | "pos.discount.override"
  | "pos.sale.void"
  | "pos.refund.create"
  | "inventory.stock.adjust";

export interface ManagerPinStatus {
  is_set: boolean;
  pin_set_at: string | null;
  locked_until: string | null;
}

export interface ApprovalSession {
  approval_token: string;
  expires_in: number;
  action: ApprovalAction;
  approver_id: string;
  approver_display_name: string;
  request_hash: string;
}

export interface ApprovalSessionRequest {
  approver_username: string;
  manager_pin: string;
  action: ApprovalAction;
  reason: string;
  request_payload: Record<string, unknown>;
}
