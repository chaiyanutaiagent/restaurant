import { useEffect, useState } from "react";
import { Network } from "@capacitor/network";
import { db, type SyncedCompletedOrder } from "@/lib/db";
import { posApi } from "@/lib/posApi";
import { categoryApi, productApi, unitApi } from "@/lib/productApi";
import { stockApi } from "@/lib/stockApi";
import type { Category, ProductListItem, Unit } from "@/types/product";
import type { SaleOrder } from "@/types/pos";
import type { StockBalance } from "@/types/stock";

type SyncedProduct = ProductListItem & { synced_at: number };
type SyncedCategory = Category & { synced_at: number };
type SyncedUnit = Unit & { synced_at: number };
type SyncedStockBalance = StockBalance & { synced_at: number };
export async function syncProductCatalog(catalogScope: "all" | "restaurant_menu" = "all"): Promise<void> {
  try {
    const limit = 100;
    let page = 1;
    let total = 0;
    const products: SyncedProduct[] = [];

    do {
      const response = await productApi.list({ page, limit, is_active: true, catalog_scope: catalogScope });
      const items = response.data.data as ProductListItem[];
      total = response.data.meta.total ?? items.length;
      products.push(...items.map((item) => ({ ...item, synced_at: Date.now() })));
      page += 1;
    } while (products.length < total);

    const [categoriesResponse, unitsResponse] = await Promise.all([
      categoryApi.list(false),
      unitApi.list()
    ]);

    const categories = (categoriesResponse.data.data as Category[]).map((item) => ({
      ...item,
      synced_at: Date.now()
    })) satisfies SyncedCategory[];
    const units = (unitsResponse.data.data as Unit[]).map((item) => ({
      ...item,
      synced_at: Date.now()
    })) satisfies SyncedUnit[];

    await db.transaction("rw", db.products, db.categories, db.units, async () => {
      await db.products.clear();
      await db.categories.clear();
      await db.units.clear();
      await db.products.bulkPut(products);
      await db.categories.bulkPut(categories);
      await db.units.bulkPut(units);
    });
  } catch {
    return;
  }
}

export async function syncStockBalances(branchId?: string): Promise<void> {
  try {
    const [balancesResponse, lowStockResponse] = await Promise.all([
      stockApi.listBalances({ branch_id: branchId }),
      stockApi.listBalances({ branch_id: branchId, low_stock_only: true })
    ]);

    const syncedAt = Date.now();
    const balances = (balancesResponse.data.data as StockBalance[]).map((item) => ({
      ...item,
      synced_at: syncedAt
    })) satisfies SyncedStockBalance[];

    const lowStockAlerts = (lowStockResponse.data.data as StockBalance[]).map((item) => ({
      id: `${item.branch_id}:${item.location_id}:${item.product_id}:${item.variant_id ?? "base"}`,
      product_id: item.product_id,
      product_name: item.product_name,
      product_sku: item.product_sku,
      qty_on_hand: Number(item.qty_on_hand),
      min_stock_qty: Number(item.min_stock_qty ?? 0),
      branch_id: item.branch_id,
      synced_at: syncedAt
    }));

    await db.transaction("rw", db.stockBalances, db.lowStockAlerts, async () => {
      await db.stockBalances.clear();
      await db.lowStockAlerts.clear();
      await db.stockBalances.bulkPut(balances);
      await db.lowStockAlerts.bulkPut(lowStockAlerts);
    });
  } catch {
    return;
  }
}

export async function syncPendingSales(): Promise<{ synced: number; failed: number }> {
  if (!navigator.onLine) {
    return { synced: 0, failed: 0 };
  }

  const pending = (await db.pendingSales.toArray()).filter((item) => !item.synced);
  if (pending.length === 0) {
    return { synced: 0, failed: 0 };
  }

  let synced = 0;
  let failed = 0;

  for (let index = 0; index < pending.length; index += 50) {
    const batch = pending.slice(index, index + 50);
    try {
      const ordersPayload = batch.map((sale) => ({
        shift_id: sale.shift_id,
        location_id: sale.location_id,
        items: sale.items.map((item) => ({
          product_id: item.product_id,
          variant_id: item.variant_id,
          qty: item.qty,
          unit_price: item.unit_price,
          original_price: item.original_price,
          discount_amount: item.discount_amount,
          discount_type: item.discount_type,
          vat_type: item.vat_type,
          vat_rate: item.vat_rate
        })),
        discount_amount: sale.discount_amount,
        discount_type: sale.discount_type,
        payment_method: sale.payment_method,
        payments: sale.payments,
        payment_reference: sale.payment_reference,
        paid_amount: sale.paid_amount,
        customer_id: sale.customer_id,
        customer_name: sale.customer_name,
        customer_phone: sale.customer_phone,
        customer_tax_id: sale.customer_tax_id,
        note: sale.note,
        is_offline: true,
        client_order_id: sale.client_order_id
      }));
      const response = await posApi.syncSales(ordersPayload);
      const orders = response.data.data as SaleOrder[];
      const syncedAt = Date.now();
      await db.transaction("rw", db.pendingSales, db.completedOrders, async () => {
        for (const sale of batch) {
          await db.pendingSales.update(sale.client_order_id, { synced: true });
        }
        await db.completedOrders.bulkPut(
          orders.map((order) => ({ ...order, synced_at: syncedAt })) satisfies SyncedCompletedOrder[]
        );
      });
      synced += batch.length;
    } catch {
      failed += batch.length;
    }
  }

  return { synced, failed };
}

let autoSyncInitialized = false;

export function initAutoSync(): void {
  if (autoSyncInitialized || typeof window === "undefined") {
    return;
  }
  autoSyncInitialized = true;
  window.addEventListener("online", () => {
    void syncProductCatalog();
    void syncStockBalances();
    void syncPendingSales();
  });
}

export function useOfflineProducts(search?: string, catalogRevision = 0): ProductListItem[] {
  const [items, setItems] = useState<ProductListItem[]>([]);

  useEffect(() => {
    let cancelled = false;

    void db.products.toArray().then((rows) => {
      if (cancelled) {
        return;
      }

      const normalized = search?.trim().toLowerCase();
      const filtered = normalized
        ? rows.filter((item) =>
            [item.name, item.sku, item.barcode ?? ""].some((value) =>
              value.toLowerCase().includes(normalized)
            )
          )
        : rows;

      setItems(filtered);
    });

    return () => {
      cancelled = true;
    };
  }, [catalogRevision, search]);

  return items;
}

export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(() => navigator.onLine);

  useEffect(() => {
    let cancelled = false;
    let removeNativeListener: (() => Promise<void>) | undefined;
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    void Network.getStatus().then((status) => {
      if (!cancelled) setIsOnline(status.connected);
    });
    void Network.addListener("networkStatusChange", (status) => {
      if (!cancelled) setIsOnline(status.connected);
    }).then((handle) => {
      removeNativeListener = () => handle.remove();
    });
    return () => {
      cancelled = true;
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      if (removeNativeListener) void removeNativeListener();
    };
  }, []);

  return isOnline;
}

export function useLowStockCount(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const updateCount = async () => {
      const next = await db.lowStockAlerts.count();
      if (!cancelled) {
        setCount(next);
      }
    };

    void updateCount();
    const interval = window.setInterval(() => {
      void updateCount();
    }, 1000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  return count;
}
