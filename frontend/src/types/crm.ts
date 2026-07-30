export interface CustomerTier {
  id: string;
  name: string;
  name_th: string;
  min_lifetime_spend: number;
  points_multiplier: number;
  color: string | null;
  benefits: string | null;
  sort_order: number;
  is_active: boolean;
}

export interface LoyaltySettings {
  id: string;
  company_id: string;
  earn_rate: number;
  earn_min_spend: number;
  redeem_rate: number;
  redeem_min_points: number;
  redeem_max_pct: number;
  points_expiry_months: number;
  enabled: boolean;
  require_phone: boolean;
}

export interface CustomerTag {
  id: string;
  name: string;
  color: string;
}

export interface Customer {
  id: string;
  company_id: string;
  customer_code: string;
  tier_id: string | null;
  tier: CustomerTier | null;
  first_name: string | null;
  last_name: string | null;
  display_name: string | null;
  phone: string | null;
  email: string | null;
  tax_id: string | null;
  date_of_birth: string | null;
  gender: string | null;
  address: string | null;
  note: string | null;
  points_balance: number;
  lifetime_spend: number;
  lifetime_points_earned: number;
  lifetime_points_redeemed: number;
  total_orders: number;
  last_purchase_at: string | null;
  is_active: boolean;
  is_blacklisted: boolean;
  tags: CustomerTag[];
  created_at: string;
}

export interface CustomerListItem {
  id: string;
  customer_code: string;
  display_name: string | null;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  email: string | null;
  tier_id: string | null;
  tier_name: string | null;
  points_balance: number;
  lifetime_spend: number;
  total_orders: number;
  last_purchase_at: string | null;
  is_active: boolean;
}

export interface CustomerSearchResult {
  id: string;
  customer_code: string;
  display_name: string | null;
  phone: string | null;
  points_balance: number;
  tier_name: string | null;
}

export interface PointsTransaction {
  id: string;
  customer_id: string;
  transaction_type: string;
  points: number;
  balance_after: number;
  reference_type: string | null;
  reference_id: string | null;
  spend_amount: number | null;
  redeem_amount: number | null;
  note: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface CustomerPurchaseHistory {
  total_orders: number;
  total_spend: number;
  avg_order_value: number;
  first_purchase_at: string | null;
  last_purchase_at: string | null;
  recent_orders: Array<{ id: string; created_at: string; total_amount: number }>;
}
