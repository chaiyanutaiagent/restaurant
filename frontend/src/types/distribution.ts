import type { SupplyChainRelease } from "@/types/supplyChainRelease";

export type DistributionModule = "restaurant_pos" | "takeaway_pos" | "retail_pos";

export type DistributionDemand = {
  id: string;
  source_module: DistributionModule;
  brand_id: string;
  brand_name: string;
  branch_id: string;
  branch_name: string;
  product_id: string;
  product_name: string;
  needed_on: string;
  requested_qty: number | string;
  allocated_qty: number | string;
  net_received_qty: number | string;
  unit_code: string;
  status: "submitted" | "partially_allocated" | "allocated" | "fulfilled" | "cancelled";
  source_type: string;
  source_id: string;
  note: string | null;
};

export type DistributionEvent = {
  id: string;
  event_type: "planned" | "dispatched" | "received" | "rejected" | "returned" | "cancelled";
  qty: number | string;
  unit_code: string;
  transfer_order_id: string | null;
  note: string | null;
  created_at: string;
};

export type DistributionShipment = {
  id: string;
  shipment_number: string;
  demand_id: string;
  transfer_order_id: string;
  transfer_number: string;
  source_module: DistributionModule;
  brand_id: string;
  brand_name: string;
  branch_id: string;
  branch_name: string;
  product_id: string;
  product_name: string;
  status: "planned" | "in_transit" | "partially_received" | "received" | "rejected" | "partially_returned" | "returned" | "cancelled";
  planned_qty: number | string;
  shipped_qty: number | string;
  received_qty: number | string;
  rejected_qty: number | string;
  returned_qty: number | string;
  in_transit_qty: number | string;
  net_received_qty: number | string;
  unit_code: string;
  unit_cost: number | string;
  dispatched_at: string | null;
  settled_at: string | null;
  note: string | null;
  events: DistributionEvent[];
};

export type DistributionSetupOptions = {
  brands: Array<{ id: string; name: string; business_type: string; source_module: DistributionModule }>;
  brand_branches: Array<{ brand_id: string; branch_id: string; branch_name: string; store_location_id: string }>;
  products: Array<{ id: string; brand_id: string; name: string; sku: string; unit_code: string | null; available_qty: number | string }>;
};

export type DistributionDashboard = {
  demands: DistributionDemand[];
  shipments: DistributionShipment[];
  setup_options: DistributionSetupOptions;
  write_enabled: boolean;
  release: SupplyChainRelease;
};

export type DistributionReport = {
  date_from: string;
  date_to: string;
  totals: Record<"planned_qty" | "shipped_qty" | "received_qty" | "rejected_qty" | "returned_qty" | "in_transit_qty" | "net_received_qty", number | string>;
  by_workspace: Array<{
    source_module: DistributionModule;
    brand_id: string;
    brand_name: string;
    branch_id: string;
    branch_name: string;
    shipment_count: number;
    planned_qty: number | string;
    shipped_qty: number | string;
    received_qty: number | string;
    rejected_qty: number | string;
    returned_qty: number | string;
    in_transit_qty: number | string;
    net_received_qty: number | string;
  }>;
  shipments: DistributionShipment[];
};
