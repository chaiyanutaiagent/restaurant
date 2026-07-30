export interface GatewayConfig {
  id: string;
  company_id: string;
  omise_public_key: string | null;
  omise_enabled: boolean;
  twoc2p_merchant_id: string | null;
  twoc2p_enabled: boolean;
  promptpay_target: string | null;
  promptpay_name: string | null;
  promptpay_enabled: boolean;
  scb_enabled: boolean;
  line_notify_enabled: boolean;
  smtp_host: string | null;
  smtp_port: number;
  smtp_username: string | null;
  smtp_from_email: string | null;
  smtp_from_name: string | null;
  smtp_enabled: boolean;
}

export interface PaymentSession {
  id: string;
  session_ref: string;
  gateway: string;
  method: string;
  amount: number;
  currency: string;
  status: string;
  reference_type: string | null;
  reference_id: string | null;
  gateway_ref: string | null;
  qr_payload: string | null;
  expires_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface NotificationLog {
  id: string;
  channel: string;
  recipient: string;
  event_type: string;
  subject: string | null;
  status: string;
  sent_at: string;
  reference_type: string | null;
  reference_id: string | null;
  error_message?: string | null;
}
