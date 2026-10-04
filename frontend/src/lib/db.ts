import Dexie, { type Table } from "dexie";
import type { Category, ProductListItem, Unit } from "@/types/product";
import type { HeldSaleDraft, PendingSale, ReplacementRuleDraft, SaleOrder } from "@/types/pos";
import type { StockBalance } from "@/types/stock";
import type { WapMenu, WapOrder, WapPaidOrderPayload } from "@/lib/wapApi";
import type {
  TakeawayCatalogRow,
  TakeawayContext,
  TakeawayRecord,
  TakeawayReceipt,
  TakeawaySalePayload,
} from "@/lib/takeawayApi";

export type PendingTransaction = {
  id?: number;
  type: string;
  payload: string;
  createdAt: string;
  syncedAt?: string;
};

export type OfflineProduct = {
  id: string;
  data: string;
  updatedAt: string;
};

export type OfflineSetting = {
  key: string;
  value: string;
};

export type LowStockAlert = {
  id: string;
  product_id: string;
  product_name: string;
  product_sku: string;
  qty_on_hand: number;
  min_stock_qty: number;
  branch_id: string;
  synced_at: number;
};

export type SyncedCompletedOrder = Omit<SaleOrder, "synced_at"> & { synced_at: number };

export type RestaurantMenuSnapshot = {
  key: string;
  company_id: string;
  branch_id: string;
  brand_slug: string;
  user_id: string;
  menu: WapMenu;
  synced_at: number;
};

export type RestaurantPendingOrderStatus =
  | "pending_sync"
  | "syncing"
  | "server_acknowledged"
  | "reconciled"
  | "needs_review"
  | "rejected"
  | "quarantined"
  | "unknown";

export type OfflineEncryptionKey = {
  key: string;
  crypto_key: CryptoKey;
  created_at: number;
};

export type EncryptedOfflineData = {
  version: 1;
  iv: string;
  ciphertext: string;
};

export type RestaurantPendingOrder = {
  client_order_id: string;
  company_id: string;
  brand_id?: string | null;
  branch_id: string;
  brand_slug: string;
  user_id: string;
  device_id?: string;
  shift_id?: string;
  station_key?: string;
  schema_version?: "offline-pos-v1";
  client_operation_id?: string;
  idempotency_key?: string;
  request_hash?: string;
  sequence_no?: number;
  operation_type?: "cash_sale";
  price_snapshot_version?: string;
  encrypted_data?: EncryptedOfflineData;
  encryption_version?: 1;
  // Legacy fields are read only so pre-WP47 queues can be quarantined safely.
  payload?: WapPaidOrderPayload;
  local_order?: WapOrder;
  server_order?: WapOrder;
  status: RestaurantPendingOrderStatus;
  attempts: number;
  last_error?: string;
  last_error_code?: string;
  next_retry_at?: number;
  server_operation_id?: string;
  acknowledged_at?: number;
  reconciled_at?: number;
  created_at: number;
  updated_at: number;
  synced_at?: number;
};

export type TakeawayWorkspaceSnapshot = {
  key: string;
  company_id: string;
  brand_id: string;
  branch_id: string;
  user_id: string;
  context: TakeawayContext;
  categories: TakeawayRecord[];
  catalog: TakeawayCatalogRow[];
  shifts: TakeawayRecord[];
  synced_at: number;
};

export type TakeawayPendingSaleStatus = "pending" | "syncing" | "needs_review" | "synced";

export type TakeawayLocalOrder = TakeawayRecord & {
  order_number: string;
  queue_number: number | null;
  total_amount: string;
  status: "offline_pending" | "paid";
  fulfillment_status: "offline_pending" | "queued";
  created_at: string;
};

export type TakeawayPendingSale = {
  client_sale_id: string;
  company_id: string;
  brand_id: string;
  branch_id: string;
  user_id: string;
  payload: TakeawaySalePayload;
  local_order: TakeawayLocalOrder;
  local_receipt: TakeawayReceipt;
  server_order?: TakeawayRecord;
  server_receipt?: TakeawayReceipt;
  pickup_token?: string | null;
  status: TakeawayPendingSaleStatus;
  attempts: number;
  last_error?: string;
  created_at: number;
  updated_at: number;
  synced_at?: number;
};

export class RestaurantDatabase extends Dexie {
  pendingTransactions!: Table<PendingTransaction, number>;
  offlineProducts!: Table<OfflineProduct, string>;
  offlineSettings!: Table<OfflineSetting, string>;
  products!: Table<ProductListItem & { synced_at: number }, string>;
  categories!: Table<Category & { synced_at: number }, string>;
  units!: Table<Unit & { synced_at: number }, string>;
  stockBalances!: Table<StockBalance & { synced_at: number }, string>;
  lowStockAlerts!: Table<LowStockAlert, string>;
  pendingSales!: Table<PendingSale, string>;
  completedOrders!: Table<SyncedCompletedOrder, string>;
  heldBills!: Table<HeldSaleDraft, string>;
  replacementRules!: Table<ReplacementRuleDraft, string>;
  restaurantMenuSnapshots!: Table<RestaurantMenuSnapshot, string>;
  restaurantPendingOrders!: Table<RestaurantPendingOrder, string>;
  offlineKeys!: Table<OfflineEncryptionKey, string>;
  takeawayWorkspaceSnapshots!: Table<TakeawayWorkspaceSnapshot, string>;
  takeawayPendingSales!: Table<TakeawayPendingSale, string>;

  public constructor() {
    super("RestaurantPOSDatabase");

    this.version(1).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value"
    });

    this.version(2).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value",
      products: "id, sku, barcode, category_id, is_active, synced_at",
      categories: "id, parent_id, synced_at",
      units: "id, code, synced_at"
    });

    this.version(3).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value",
      products: "id, sku, barcode, category_id, is_active, synced_at",
      categories: "id, parent_id, synced_at",
      units: "id, code, synced_at",
      stockBalances: "id, product_id, location_id, branch_id, synced_at",
      lowStockAlerts: "id, product_id, branch_id, synced_at"
    });

    this.version(4).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value",
      products: "id, sku, barcode, category_id, is_active, synced_at",
      categories: "id, parent_id, synced_at",
      units: "id, code, synced_at",
      stockBalances: "id, product_id, location_id, branch_id, synced_at",
      lowStockAlerts: "id, product_id, branch_id, synced_at",
      pendingSales: "client_order_id, synced, created_at",
      completedOrders: "id, shift_id, created_at, synced_at"
    });

    this.version(5).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value",
      products: "id, sku, barcode, category_id, is_active, synced_at",
      categories: "id, parent_id, synced_at",
      units: "id, code, synced_at",
      stockBalances: "id, product_id, location_id, branch_id, synced_at",
      lowStockAlerts: "id, product_id, branch_id, synced_at",
      pendingSales: "client_order_id, synced, created_at",
      completedOrders: "id, shift_id, created_at, synced_at",
      heldBills: "id, shift_id, location_id, held_at"
    });

    this.version(6).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value",
      products: "id, sku, barcode, category_id, is_active, synced_at",
      categories: "id, parent_id, synced_at",
      units: "id, code, synced_at",
      stockBalances: "id, product_id, location_id, branch_id, synced_at",
      lowStockAlerts: "id, product_id, branch_id, synced_at",
      pendingSales: "client_order_id, synced, created_at",
      completedOrders: "id, shift_id, created_at, synced_at",
      heldBills: "id, shift_id, location_id, held_at",
      replacementRules: "id, branch_id, source_product_id, replacement_product_id, created_at"
    });

    this.version(7).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value",
      products: "id, sku, barcode, category_id, is_active, synced_at",
      categories: "id, parent_id, synced_at",
      units: "id, code, synced_at",
      stockBalances: "id, product_id, location_id, branch_id, synced_at",
      lowStockAlerts: "id, product_id, branch_id, synced_at",
      pendingSales: "client_order_id, synced, created_at",
      completedOrders: "id, shift_id, created_at, synced_at",
      heldBills: "id, shift_id, location_id, held_at",
      replacementRules: "id, branch_id, source_product_id, replacement_product_id, created_at",
      restaurantMenuSnapshots: "key, company_id, branch_id, brand_slug, user_id, synced_at",
      restaurantPendingOrders: "client_order_id, [company_id+branch_id+brand_slug], status, created_at, updated_at"
    });

    this.version(8).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value",
      products: "id, sku, barcode, category_id, is_active, synced_at",
      categories: "id, parent_id, synced_at",
      units: "id, code, synced_at",
      stockBalances: "id, product_id, location_id, branch_id, synced_at",
      lowStockAlerts: "id, product_id, branch_id, synced_at",
      pendingSales: "client_order_id, synced, created_at",
      completedOrders: "id, shift_id, created_at, synced_at",
      heldBills: "id, shift_id, location_id, held_at",
      replacementRules: "id, branch_id, source_product_id, replacement_product_id, created_at",
      restaurantMenuSnapshots: "key, company_id, branch_id, brand_slug, user_id, synced_at",
      restaurantPendingOrders: "client_order_id, [company_id+branch_id+brand_slug], status, created_at, updated_at",
      takeawayWorkspaceSnapshots: "key, [company_id+brand_id+branch_id], user_id, synced_at",
      takeawayPendingSales: "client_sale_id, [company_id+brand_id+branch_id], status, created_at, updated_at"
    });

    this.version(9).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value",
      products: "id, sku, barcode, category_id, is_active, synced_at",
      categories: "id, parent_id, synced_at",
      units: "id, code, synced_at",
      stockBalances: "id, product_id, location_id, branch_id, synced_at",
      lowStockAlerts: "id, product_id, branch_id, synced_at",
      pendingSales: "client_order_id, synced, created_at",
      completedOrders: "id, shift_id, created_at, synced_at",
      heldBills: "id, shift_id, location_id, held_at",
      replacementRules: "id, branch_id, source_product_id, replacement_product_id, created_at",
      restaurantMenuSnapshots: "key, company_id, branch_id, brand_slug, user_id, synced_at",
      restaurantPendingOrders: "client_order_id, [company_id+branch_id+brand_slug], status, created_at, updated_at, next_retry_at, sequence_no",
      offlineKeys: "key, created_at",
      takeawayWorkspaceSnapshots: "key, [company_id+brand_id+branch_id], user_id, synced_at",
      takeawayPendingSales: "client_sale_id, [company_id+brand_id+branch_id], status, created_at, updated_at"
    }).upgrade(async (transaction) => {
      await transaction.table("restaurantPendingOrders").toCollection().modify((row: RestaurantPendingOrder) => {
        if (!row.encrypted_data) {
          row.status = "quarantined";
          row.last_error_code = "legacy_plaintext_outbox";
          row.last_error = "รายการจากระบบเดิมถูกกักไว้เพื่อป้องกันข้อมูลผิดรูปแบบ กรุณาตรวจสอบกับผู้ดูแล";
        }
      });
    });

    this.version(10).stores({
      pendingTransactions: "++id, type, payload, createdAt, syncedAt",
      offlineProducts: "id, data, updatedAt",
      offlineSettings: "key, value",
      products: "id, sku, barcode, category_id, is_active, synced_at",
      categories: "id, parent_id, synced_at",
      units: "id, code, synced_at",
      stockBalances: "id, product_id, location_id, branch_id, synced_at",
      lowStockAlerts: "id, product_id, branch_id, synced_at",
      pendingSales: "client_order_id, [company_id+branch_id+business_type], status, synced, created_at, updated_at",
      completedOrders: "id, shift_id, created_at, synced_at",
      heldBills: "id, shift_id, location_id, held_at",
      replacementRules: "id, branch_id, source_product_id, replacement_product_id, created_at",
      restaurantMenuSnapshots: "key, company_id, branch_id, brand_slug, user_id, synced_at",
      restaurantPendingOrders: "client_order_id, [company_id+branch_id+brand_slug], status, created_at, updated_at, next_retry_at, sequence_no",
      offlineKeys: "key, created_at",
      takeawayWorkspaceSnapshots: "key, [company_id+brand_id+branch_id], user_id, synced_at",
      takeawayPendingSales: "client_sale_id, [company_id+brand_id+branch_id], status, created_at, updated_at"
    }).upgrade(async (transaction) => {
      await transaction.table("pendingSales").toCollection().modify((row: PendingSale) => {
        row.updated_at = row.updated_at ?? row.created_at;
        row.attempt_count = row.attempt_count ?? 0;
        row.status = row.synced ? "synced" : "needs_review";
        if (!row.synced && (!row.company_id || !row.branch_id || !row.business_type)) {
          row.last_error_code = "legacy_context_missing";
          row.last_error_message = "รายการเดิมไม่มี Company/Branch context และถูกกักไว้ ห้ามส่งอัตโนมัติ";
        }
      });
    });
  }
}

export const db = new RestaurantDatabase();
