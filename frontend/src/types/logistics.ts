export type ShipmentStatus =
  "pending" | "packed" | "picked_up" | "in_transit" | "delivered" | "returned" | "cancelled";

export interface Carrier {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
  tracking_url: string | null;
  is_cod: boolean;
  is_active: boolean;
}

export interface ShippingEstimate {
  carrier_id: string;
  carrier_code: string;
  carrier_name: string;
  service_name: string;
  cost: number;
  cod_fee: number;
}

export interface ShipmentItem {
  id: string;
  product_id: string | null;
  product_name: string;
  sku: string | null;
  qty: number;
  unit_price: number | null;
}

export interface ShipmentEvent {
  id: string;
  shipment_id?: string;
  status: string;
  location: string | null;
  note: string | null;
  event_at: string;
}

export interface Shipment {
  id: string;
  shipment_number: string;
  status: ShipmentStatus;
  branch_id: string;
  carrier_id: string;
  carrier_name: string;
  carrier_code: string;
  tracking_url: string | null;
  sale_order_id: string | null;
  external_order_id: string | null;
  sender_name: string;
  sender_phone: string;
  sender_address: string;
  recipient_name: string;
  recipient_phone: string;
  recipient_address: string;
  weight_grams: number;
  service_name: string | null;
  is_cod: boolean;
  cod_amount: number;
  shipping_cost: number;
  tracking_number: string | null;
  picked_up_at: string | null;
  delivered_at: string | null;
  note: string | null;
  created_at: string;
  items: ShipmentItem[];
  events: ShipmentEvent[];
}

export interface ShipmentListItem {
  id: string;
  shipment_number: string;
  status: ShipmentStatus;
  carrier_name: string;
  carrier_code: string;
  recipient_name: string;
  recipient_phone: string;
  tracking_number: string | null;
  is_cod: boolean;
  cod_amount: number;
  shipping_cost: number;
  weight_grams: number;
  created_at: string;
}
