import { Network } from "@capacitor/network";
import { db, type RestaurantPendingOrder } from "@/lib/db";
import { wapApi, type WapMenu, type WapOrder, type WapPaidOrderPayload } from "@/lib/wapApi";
import { useAuthStore } from "@/stores/auth.store";
import { useDeviceStore } from "@/stores/device.store";

type RestaurantScope = {
  companyId: string;
  branchId: string;
  userId: string;
};

export type RestaurantQueuedOrderResult = {
  order: WapOrder;
  status: RestaurantPendingOrder["status"];
  error?: string;
};

export type RestaurantOutboxSummary = {
  pending: number;
  needsReview: number;
  syncing: number;
  latestError?: string;
};

const syncPromises = new Map<string, Promise<RestaurantOutboxSummary>>();

function currentScope(): RestaurantScope {
  const { companyId, branchId, user } = useAuthStore.getState();
  if (!companyId || !branchId || !user?.id) {
    throw new Error("กรุณาเข้าสู่ระบบและเลือกสาขาก่อนขาย");
  }
  return { companyId, branchId, userId: user.id };
}

function normalizedBrandSlug(brandSlug?: string): string {
  return brandSlug ?? "_unbranded";
}

function scopeKey(brandSlug?: string, scope = currentScope()): string {
  return `${scope.companyId}:${scope.branchId}:${normalizedBrandSlug(brandSlug)}:${scope.userId}`;
}

function isBrowserOnline(): boolean {
  return typeof navigator === "undefined" || navigator.onLine;
}

async function isNetworkConnected(): Promise<boolean> {
  try {
    return (await Network.getStatus()).connected;
  } catch {
    return isBrowserOnline();
  }
}

function randomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function installationId(): Promise<string> {
  const key = "restaurant.android.installation_id";
  const existing = await db.offlineSettings.get(key);
  if (existing?.value) return existing.value;
  const value = randomId();
  await db.offlineSettings.put({ key, value });
  return value;
}

function assertCurrentOfflineAuthorization(menu: WapMenu, scope: RestaurantScope): void {
  if (
    menu.offline_policy_version !== 1
    || !menu.offline_authorization
    || !menu.offline_authorization_expires_at
  ) {
    throw new Error("เมนูในเครื่องยังไม่มีสิทธิ์ขายออฟไลน์ กรุณาต่ออินเทอร์เน็ตและโหลดหน้าขายใหม่");
  }
  const expiresAt = new Date(menu.offline_authorization_expires_at).getTime();
  if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
    throw new Error("สิทธิ์ขายออฟไลน์หมดอายุ กรุณาต่ออินเทอร์เน็ตและลงชื่อพนักงานใหม่");
  }
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/counter")) {
    const device = useDeviceStore.getState().device;
    if (
      !device
      || device.device_type !== "counter"
      || device.branch_id !== scope.branchId
      || menu.offline_device_id !== device.device_id
    ) {
      throw new Error("สิทธิ์ขายออฟไลน์ไม่ตรงกับ Counter เครื่องนี้ กรุณาต่ออินเทอร์เน็ตและโหลดใหม่");
    }
  }
}

export async function fetchAndCacheRestaurantMenu(brandSlug?: string): Promise<WapMenu> {
  const scope = currentScope();
  const menu = (await wapApi.menu(brandSlug)).data.data;
  await db.restaurantMenuSnapshots.put({
    key: scopeKey(brandSlug, scope),
    company_id: scope.companyId,
    branch_id: scope.branchId,
    brand_slug: normalizedBrandSlug(brandSlug),
    user_id: scope.userId,
    menu,
    synced_at: Date.now(),
  });
  return menu;
}

export async function getCachedRestaurantMenu(brandSlug?: string): Promise<WapMenu | null> {
  return (await db.restaurantMenuSnapshots.get(scopeKey(brandSlug)))?.menu ?? null;
}

export async function loadRestaurantMenu(brandSlug?: string): Promise<WapMenu> {
  if (await isNetworkConnected()) {
    try {
      return await fetchAndCacheRestaurantMenu(brandSlug);
    } catch {
      // A device can report online before the API is reachable. Fall through to cache.
    }
  }
  const cached = await getCachedRestaurantMenu(brandSlug);
  if (!cached) {
    throw new Error("ยังไม่มีเมนูในเครื่อง กรุณาต่ออินเทอร์เน็ตและเปิดหน้าขายอย่างน้อยหนึ่งครั้ง");
  }
  return cached;
}

function localQueueLabel(clientOrderId: string): string {
  const suffix = clientOrderId.replace(/[^a-zA-Z0-9]/g, "").slice(-5).toUpperCase();
  return `O${suffix}`;
}

function buildLocalOrder(
  payload: WapPaidOrderPayload & { client_order_id: string; local_created_at: string },
  menu: WapMenu,
  userId: string,
): WapOrder {
  const products = new Map(menu.products.map((product) => [product.id, product]));
  const queueDisplay = localQueueLabel(payload.client_order_id);
  const items = payload.items.map((item) => {
    const product = products.get(item.product_id);
    return {
      product_id: item.product_id,
      product_name: product?.name ?? "สินค้าออฟไลน์",
      qty: item.qty,
      unit_price: product?.selling_price ?? 0,
      special_request: item.special_request ?? null,
    };
  });
  const totalAmount = Number(payload.paid_amount || 0);
  return {
    session_id: `local-session:${payload.client_order_id}`,
    order_id: `local-order:${payload.client_order_id}`,
    sale_order_id: `local-sale:${payload.client_order_id}`,
    sale_order_number: `LOCAL-${queueDisplay}`,
    opened_by: userId,
    cashier_user_id: userId,
    queue_number: null,
    queue_display: queueDisplay,
    status: "offline_pending",
    customer_name: payload.customer_name ?? null,
    customer_phone: payload.customer_phone ?? null,
    subtotal: totalAmount,
    total_amount: totalAmount,
    paid_amount: totalAmount,
    change_amount: 0,
    payment_method: payload.payment_method,
    customer_slip_printed_at: null,
    kitchen_slip_printed_at: null,
    kitchen_sent_at: null,
    recipe_stock_status: null,
    recipe_stock_warnings: [],
    created_at: payload.local_created_at,
    client_order_id: payload.client_order_id,
    is_offline_pending: true,
    items,
  };
}

function rowMatchesScope(row: RestaurantPendingOrder, brandSlug: string | undefined, scope: RestaurantScope): boolean {
  return row.company_id === scope.companyId
    && row.branch_id === scope.branchId
    && row.brand_slug === normalizedBrandSlug(brandSlug)
    && row.user_id === scope.userId;
}

export async function getRestaurantOutboxSummary(brandSlug?: string): Promise<RestaurantOutboxSummary> {
  const scope = currentScope();
  const rows = (await db.restaurantPendingOrders.toArray()).filter((row) => rowMatchesScope(row, brandSlug, scope));
  return {
    pending: rows.filter((row) => row.status === "pending").length,
    syncing: rows.filter((row) => row.status === "syncing").length,
    needsReview: rows.filter((row) => row.status === "needs_review").length,
    latestError: rows
      .filter((row) => row.status === "needs_review" && row.last_error)
      .sort((a, b) => b.updated_at - a.updated_at)[0]?.last_error,
  };
}

async function performRestaurantSync(brandSlug?: string): Promise<RestaurantOutboxSummary> {
  if (!await isNetworkConnected()) return getRestaurantOutboxSummary(brandSlug);
  const scope = currentScope();
  const candidates = (await db.restaurantPendingOrders.toArray())
    .filter((row) => rowMatchesScope(row, brandSlug, scope))
    .filter((row) => row.status === "pending" || row.status === "syncing")
    .sort((a, b) => a.created_at - b.created_at);

  for (let index = 0; index < candidates.length; index += 50) {
    const batch = candidates.slice(index, index + 50);
    const updatedAt = Date.now();
    await db.restaurantPendingOrders.bulkPut(batch.map((row) => ({
      ...row,
      status: "syncing" as const,
      attempts: row.attempts + 1,
      updated_at: updatedAt,
    })));

    try {
      const response = await wapApi.syncPaidOrders(brandSlug, batch.map((row) => row.payload));
      const results = new Map(response.data.data.results.map((result) => [result.client_order_id, result]));
      await db.transaction("rw", db.restaurantPendingOrders, async () => {
        for (const row of batch) {
          const result = results.get(row.client_order_id);
          if (!result) {
            await db.restaurantPendingOrders.update(row.client_order_id, {
              status: "pending",
              last_error: "เซิร์ฟเวอร์ไม่ตอบผลของรายการนี้",
              updated_at: Date.now(),
            });
            continue;
          }
          if (result.status === "synced" && result.order) {
            await db.restaurantPendingOrders.update(row.client_order_id, {
              status: "synced",
              server_order: result.order,
              last_error: undefined,
              synced_at: Date.now(),
              updated_at: Date.now(),
            });
            continue;
          }
          await db.restaurantPendingOrders.update(row.client_order_id, {
            status: "needs_review",
            last_error: result.error ?? "รายการต้องตรวจสอบก่อนบันทึก",
            updated_at: Date.now(),
          });
        }
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
      await db.transaction("rw", db.restaurantPendingOrders, async () => {
        for (const row of batch) {
          await db.restaurantPendingOrders.update(row.client_order_id, {
            status: "pending",
            last_error: message,
            updated_at: Date.now(),
          });
        }
      });
      break;
    }
  }
  return getRestaurantOutboxSummary(brandSlug);
}

export function syncRestaurantPendingOrders(brandSlug?: string): Promise<RestaurantOutboxSummary> {
  const key = scopeKey(brandSlug);
  const active = syncPromises.get(key);
  if (active) return active;
  const promise = performRestaurantSync(brandSlug).finally(() => syncPromises.delete(key));
  syncPromises.set(key, promise);
  return promise;
}

export async function queueRestaurantOrder(
  brandSlug: string | undefined,
  payload: WapPaidOrderPayload,
  menu: WapMenu,
): Promise<RestaurantQueuedOrderResult> {
  const scope = currentScope();
  assertCurrentOfflineAuthorization(menu, scope);
  const clientOrderId = `${await installationId()}:${randomId()}`;
  const localCreatedAt = new Date().toISOString();
  const queuedPayload: WapPaidOrderPayload & { client_order_id: string; local_created_at: string } = {
    ...payload,
    shift_id: menu.shift_id ?? payload.shift_id,
    location_id: menu.location_id ?? payload.location_id,
    client_order_id: clientOrderId,
    local_created_at: localCreatedAt,
    offline_policy_version: menu.offline_policy_version,
    offline_authorization: menu.offline_authorization,
    is_offline: true,
  };
  const localOrder = buildLocalOrder(queuedPayload, menu, scope.userId);
  const now = Date.now();
  await db.restaurantPendingOrders.put({
    client_order_id: clientOrderId,
    company_id: scope.companyId,
    branch_id: scope.branchId,
    brand_slug: normalizedBrandSlug(brandSlug),
    user_id: scope.userId,
    payload: queuedPayload,
    local_order: localOrder,
    status: "pending",
    attempts: 0,
    created_at: now,
    updated_at: now,
  });

  if (await isNetworkConnected()) {
    await syncRestaurantPendingOrders(brandSlug);
  }
  const saved = await db.restaurantPendingOrders.get(clientOrderId);
  if (saved?.status === "synced" && saved.server_order) {
    return { order: saved.server_order, status: "synced" };
  }
  return {
    order: saved?.local_order ?? localOrder,
    status: saved?.status ?? "pending",
    error: saved?.last_error,
  };
}

export async function markRestaurantLocalSlip(
  clientOrderId: string,
  type: "customer" | "kitchen",
): Promise<WapOrder> {
  const row = await db.restaurantPendingOrders.get(clientOrderId);
  if (!row) throw new Error("ไม่พบออเดอร์ออฟไลน์ในเครื่อง");
  const effectiveOrder = row.server_order ?? row.local_order;
  if (type === "kitchen" && !effectiveOrder.customer_slip_printed_at) {
    throw new Error("กรุณาพิมพ์สลิปลูกค้าก่อนส่งออเดอร์เข้าครัว");
  }
  if (row.status === "synced" && row.server_order && await isNetworkConnected()) {
    try {
      const serverOrder = type === "customer"
        ? (await wapApi.markCustomerSlip(row.server_order.session_id)).data.data
        : (await wapApi.markKitchenSlip(row.server_order.session_id)).data.data;
      await db.restaurantPendingOrders.update(clientOrderId, {
        server_order: serverOrder,
        updated_at: Date.now(),
      });
      return serverOrder;
    } catch {
      // Preserve the local print event and re-submit the idempotent order later.
    }
  }
  const printedAt = new Date().toISOString();
  const localOrder: WapOrder = type === "customer"
    ? { ...row.local_order, customer_slip_printed_at: printedAt }
    : {
        ...row.local_order,
        kitchen_slip_printed_at: printedAt,
        kitchen_sent_at: printedAt,
      };
  const payload = type === "customer"
    ? { ...row.payload, local_customer_slip_printed_at: printedAt }
    : { ...row.payload, local_kitchen_slip_printed_at: printedAt };
  await db.restaurantPendingOrders.update(clientOrderId, {
    local_order: localOrder,
    payload,
    status: row.status === "synced" ? "pending" : row.status,
    updated_at: Date.now(),
  });
  return localOrder;
}

export async function hasUnsyncedRestaurantOrders(brandSlug?: string): Promise<boolean> {
  const summary = await getRestaurantOutboxSummary(brandSlug);
  return summary.pending + summary.syncing + summary.needsReview > 0;
}

export async function getQueuedRestaurantOrder(clientOrderId: string): Promise<WapOrder | null> {
  const row = await db.restaurantPendingOrders.get(clientOrderId);
  return row?.server_order ?? row?.local_order ?? null;
}

export async function retryRestaurantNeedsReview(brandSlug?: string): Promise<RestaurantOutboxSummary> {
  const scope = currentScope();
  const rows = (await db.restaurantPendingOrders.toArray())
    .filter((row) => rowMatchesScope(row, brandSlug, scope) && row.status === "needs_review");
  await db.restaurantPendingOrders.bulkPut(rows.map((row) => ({
    ...row,
    status: "pending" as const,
    last_error: undefined,
    updated_at: Date.now(),
  })));
  return syncRestaurantPendingOrders(brandSlug);
}
