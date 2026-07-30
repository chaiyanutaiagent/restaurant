export interface APIKey {
  id: string;
  company_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  is_active: boolean;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
  revoked_at: string | null;
}

export interface APIKeyCreated {
  key: APIKey;
  full_key: string;
}

export interface WebhookEndpoint {
  id: string;
  company_id: string;
  name: string;
  url: string;
  events: string[];
  is_active: boolean;
  last_triggered_at: string | null;
  failure_count: number;
  created_at: string;
}

export interface WebhookDelivery {
  id: string;
  webhook_id: string;
  event_type: string;
  response_status: number | null;
  attempt_count: number;
  delivered_at: string | null;
  failed_at: string | null;
  next_retry_at: string | null;
  created_at: string;
}

export interface ExternalOrder {
  id: string;
  source: string;
  external_order_id: string;
  status: string;
  customer_name: string | null;
  customer_phone: string | null;
  total_amount: number;
  payment_status: string | null;
  sale_order_id: string | null;
  received_at: string;
  processed_at: string | null;
}
