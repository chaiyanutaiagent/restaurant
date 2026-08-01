export type DeviceType = "counter" | "kitchen" | "pickup";
export type DeviceStatus = "pending_pairing" | "pairing_expired" | "paired" | "revoked";

export interface DeviceContext {
  device_id: string;
  company_id: string;
  brand_id: string;
  branch_id: string;
  device_code: string;
  name: string;
  device_type: DeviceType;
  station_key: string | null;
  business_type: "restaurant";
  target_database: "restaurant";
  credential_version: number;
  paired_at: string;
  last_seen_at: string;
}

export interface DevicePairResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  device: DeviceContext;
}

export interface DeviceRead {
  id: string;
  company_id: string;
  branch_id: string;
  device_code: string;
  name: string;
  device_type: DeviceType;
  station_key: string | null;
  status: DeviceStatus;
  credential_version: number;
  pairing_expires_at: string | null;
  paired_at: string | null;
  last_seen_at: string | null;
  revoked_at: string | null;
  revocation_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeviceProvisioning {
  device: DeviceRead;
  pairing_pin: string;
  pairing_expires_at: string;
  pairing_qr_payload: string;
}

export interface DeviceWorkspaceBootstrap {
  workspace: DeviceType;
  device: DeviceContext;
  branch: { id: string; code: string; name: string };
  station_key: string | null;
  queue_prefix: string;
  requires_staff_login: boolean;
  capabilities: string[];
}
