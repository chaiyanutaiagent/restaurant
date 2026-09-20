import axios from "axios";
import { Network } from "@capacitor/network";
import { db, type RestaurantPendingOrder, type RestaurantPendingOrderStatus } from "@/lib/db";
import { decryptOfflineValue, encryptOfflineValue } from "@/lib/secureOfflineStore";
import { wapApi, type WapMenu, type WapOrder, type WapPaidOrderPayload } from "@/lib/wapApi";
import { useAuthStore } from "@/stores/auth.store";
import { useDeviceStore } from "@/stores/device.store";

type RestaurantScope = { companyId: string; branchId: string; userId: string };
type EncryptedOrderBundle = { payload: WapPaidOrderPayload; local_order: WapOrder; server_order?: WapOrder };

export type RestaurantQueuedOrderResult = { order: WapOrder; status: RestaurantPendingOrderStatus; error?: string };
export type RestaurantOutboxSummary = {
  pending: number;
  syncing: number;
  acknowledged: number;
  reconciled: number;
  needsReview: number;
  rejected: number;
  quarantined: number;
  unknown: number;
  latestError?: string;
  lastSyncAt?: number;
};

const syncPromises = new Map<string, Promise<RestaurantOutboxSummary>>();
const ACTIVE_SYNC_STATES: RestaurantPendingOrderStatus[] = ["pending_sync", "syncing", "server_acknowledged", "unknown"];
const BACKOFF_SECONDS = [1, 2, 5, 10, 30, 300];
const RETENTION_MS = 7 * 24 * 60 * 60 * 1000;

function currentScope(): RestaurantScope {
  const { companyId, branchId, user } = useAuthStore.getState();
  if (!companyId || !branchId || !user?.id) throw new Error("กรุณาเข้าสู่ระบบและเลือกสาขาก่อนขาย");
  return { companyId, branchId, userId: user.id };
}

function normalizedBrandSlug(brandSlug?: string): string { return brandSlug ?? "_unbranded"; }
function scopeKey(brandSlug?: string, scope = currentScope()): string {
  return `${scope.companyId}:${scope.branchId}:${normalizedBrandSlug(brandSlug)}:${scope.userId}`;
}
function isBrowserOnline(): boolean { return typeof navigator === "undefined" || navigator.onLine; }
async function isNetworkConnected(): Promise<boolean> {
  try { return (await Network.getStatus()).connected; } catch { return isBrowserOnline(); }
}
function randomId(): string {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function assertCurrentOfflineAuthorization(menu: WapMenu, scope: RestaurantScope): void {
  const device = useDeviceStore.getState().device;
  if (!menu.offline_mode_enabled) throw new Error("สาขาหรือบริษัทนี้ยังไม่ได้เปิดโหมดออฟไลน์ UAT");
  if (menu.offline_policy_version !== 1 || !menu.offline_authorization || !menu.offline_authorization_expires_at || !menu.offline_snapshot_version) {
    throw new Error("เมนูในเครื่องยังไม่มีสิทธิ์ขายออฟไลน์ กรุณาต่ออินเทอร์เน็ตและโหลดใหม่");
  }
  if (new Date(menu.offline_authorization_expires_at).getTime() <= Date.now()) {
    throw new Error("สิทธิ์ขายออฟไลน์หมดอายุ กรุณาต่ออินเทอร์เน็ตและลงชื่อพนักงานใหม่");
  }
  if (!device || device.device_type !== "counter" || device.branch_id !== scope.branchId
    || device.company_id !== scope.companyId || menu.offline_device_id !== device.device_id) {
    throw new Error("ต้องใช้ Counter ที่จับคู่กับ Company/Branch นี้จึงจะขายออฟไลน์ได้");
  }
}

export async function fetchAndCacheRestaurantMenu(brandSlug?: string): Promise<WapMenu> {
  const scope = currentScope();
  const menu = (await wapApi.menu(brandSlug)).data.data;
  await db.restaurantMenuSnapshots.put({
    key: scopeKey(brandSlug, scope), company_id: scope.companyId, branch_id: scope.branchId,
    brand_slug: normalizedBrandSlug(brandSlug), user_id: scope.userId, menu, synced_at: Date.now(),
  });
  return menu;
}
export async function getCachedRestaurantMenu(brandSlug?: string): Promise<WapMenu | null> {
  return (await db.restaurantMenuSnapshots.get(scopeKey(brandSlug)))?.menu ?? null;
}
export async function loadRestaurantMenu(brandSlug?: string): Promise<WapMenu> {
  if (await isNetworkConnected()) {
    try { return await fetchAndCacheRestaurantMenu(brandSlug); } catch { /* Device can report online before API is reachable. */ }
  }
  const cached = await getCachedRestaurantMenu(brandSlug);
  if (!cached) throw new Error("ยังไม่มีเมนูในเครื่อง กรุณาต่ออินเทอร์เน็ตและเปิดหน้าขายอย่างน้อยหนึ่งครั้ง");
  return cached;
}

function localQueueLabel(clientOrderId: string): string {
  return `O${clientOrderId.replace(/[^a-zA-Z0-9]/g, "").slice(-5).toUpperCase()}`;
}
function buildLocalOrder(
  payload: WapPaidOrderPayload & { client_order_id: string; local_created_at: string },
  menu: WapMenu,
  userId: string,
): WapOrder {
  const products = new Map(menu.products.map((product) => [product.id, product]));
  const queueDisplay = localQueueLabel(payload.client_order_id);
  const items = payload.items.map((item) => ({
    product_id: item.product_id,
    product_name: products.get(item.product_id)?.name ?? "สินค้าออฟไลน์",
    qty: item.qty,
    unit_price: products.get(item.product_id)?.selling_price ?? 0,
    special_request: item.special_request ?? null,
  }));
  const totalAmount = items.reduce((sum, item) => sum + Number(item.unit_price) * item.qty, 0);
  return {
    session_id: `local-session:${payload.client_order_id}`, order_id: `local-order:${payload.client_order_id}`,
    sale_order_id: `local-sale:${payload.client_order_id}`, sale_order_number: `LOCAL-${queueDisplay}`,
    opened_by: userId, cashier_user_id: userId, queue_number: null, queue_display: queueDisplay,
    status: "offline_pending", customer_name: payload.customer_name ?? null, customer_phone: payload.customer_phone ?? null,
    subtotal: totalAmount, total_amount: totalAmount, paid_amount: Number(payload.paid_amount),
    change_amount: Math.max(Number(payload.paid_amount) - totalAmount, 0), payment_method: payload.payment_method,
    customer_slip_printed_at: null, kitchen_slip_printed_at: null, kitchen_sent_at: null,
    recipe_stock_status: null, recipe_stock_warnings: [], created_at: payload.local_created_at,
    client_order_id: payload.client_order_id, is_offline_pending: true, items,
  };
}

function rowMatchesScope(row: RestaurantPendingOrder, brandSlug: string | undefined, scope: RestaurantScope): boolean {
  return row.company_id === scope.companyId && row.branch_id === scope.branchId
    && row.brand_slug === normalizedBrandSlug(brandSlug) && row.user_id === scope.userId;
}
function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
function fixed(value: number | string | undefined, places: number): string | null {
  return value == null ? null : Number(value).toFixed(places);
}
async function canonicalRequestHash(payload: WapPaidOrderPayload): Promise<string> {
  const document = {
    schema_version: payload.schema_version ?? null,
    client_operation_id: payload.client_operation_id ?? null,
    idempotency_key: payload.idempotency_key ?? null,
    company_id: payload.company_id ?? null,
    brand_id: payload.brand_id ?? null,
    branch_id: payload.branch_id ?? null,
    station_key: payload.station_key ?? null,
    shift_id: payload.shift_id ?? null,
    operation_type: payload.operation_type ?? null,
    sequence_no: payload.sequence_no ?? null,
    created_at_device: payload.local_created_at ?? null,
    price_snapshot_version: payload.price_snapshot_version ?? null,
    currency: payload.currency ?? null,
    authorization_digest: await sha256(payload.offline_authorization ?? ""),
    payload: {
      items: payload.items.map((item) => ({
        product_id: item.product_id, qty: item.qty, special_request: item.special_request ?? null,
        expected_unit_price: fixed(item.expected_unit_price, 4), expected_price_version: item.expected_price_version ?? null,
      })),
      payment_method: payload.payment_method,
      paid_amount: fixed(payload.paid_amount, 2),
      payments: (payload.payments ?? []).map((payment) => ({
        payment_method: payment.payment_method, amount: fixed(payment.amount, 2), reference_no: payment.reference_no ?? null,
      })),
      customer_name: payload.customer_name ?? null,
      customer_phone: payload.customer_phone ?? null,
      customer_tax_id: payload.customer_tax_id ?? null,
      note: payload.note ?? null,
      location_id: payload.location_id ?? null,
    },
  };
  return sha256(stableJson(document));
}
async function nextSequence(deviceId: string, shiftId: string): Promise<number> {
  const key = `restaurant.offline.sequence:${deviceId}:${shiftId}`;
  return db.transaction("rw", db.offlineSettings, async () => {
    const current = Number((await db.offlineSettings.get(key))?.value ?? "0") + 1;
    await db.offlineSettings.put({ key, value: String(current) });
    return current;
  });
}
async function decryptRow(row: RestaurantPendingOrder): Promise<EncryptedOrderBundle> {
  if (!row.encrypted_data) throw new Error("legacy_plaintext_outbox");
  return decryptOfflineValue<EncryptedOrderBundle>(row.encrypted_data, row.client_order_id);
}
async function quarantine(row: RestaurantPendingOrder, code: string, message: string): Promise<void> {
  await db.restaurantPendingOrders.update(row.client_order_id, {
    status: "quarantined", last_error_code: code, last_error: message, updated_at: Date.now(),
  });
}

export async function getRestaurantOutboxSummary(brandSlug?: string): Promise<RestaurantOutboxSummary> {
  const scope = currentScope();
  const rows = (await db.restaurantPendingOrders.toArray()).filter((row) => rowMatchesScope(row, brandSlug, scope));
  const count = (status: RestaurantPendingOrderStatus) => rows.filter((row) => row.status === status).length;
  const errored = rows.filter((row) => row.last_error).sort((a, b) => b.updated_at - a.updated_at);
  const synced = rows.filter((row) => row.reconciled_at).sort((a, b) => (b.reconciled_at ?? 0) - (a.reconciled_at ?? 0));
  return {
    pending: count("pending_sync"), syncing: count("syncing"), acknowledged: count("server_acknowledged"),
    reconciled: count("reconciled"), needsReview: count("needs_review"), rejected: count("rejected"),
    quarantined: count("quarantined"), unknown: count("unknown"), latestError: errored[0]?.last_error,
    lastSyncAt: synced[0]?.reconciled_at,
  };
}
function nextRetryAt(attempts: number): number {
  const seconds = BACKOFF_SECONDS[Math.min(attempts, BACKOFF_SECONDS.length - 1)];
  return Date.now() + seconds * 1000 + Math.floor(Math.random() * 250);
}
type SyncResult = Awaited<ReturnType<typeof wapApi.syncPaidOrders>>["data"]["data"]["results"][number];
async function applyServerResult(row: RestaurantPendingOrder, result: SyncResult): Promise<void> {
  const bundle = await decryptRow(row);
  const state = result.sync_state ?? (result.status === "synced" ? "reconciled" : result.status);
  const now = Date.now();
  await db.restaurantPendingOrders.update(row.client_order_id, {
    status: state === "purged" ? "reconciled" : state,
    encrypted_data: await encryptOfflineValue({ ...bundle, server_order: result.order ?? bundle.server_order }, row.client_order_id),
    server_operation_id: result.operation_id ?? row.server_operation_id,
    acknowledged_at: result.acknowledged_at ? new Date(result.acknowledged_at).getTime() : row.acknowledged_at,
    reconciled_at: result.reconciled_at ? new Date(result.reconciled_at).getTime() : state === "reconciled" ? now : row.reconciled_at,
    synced_at: state === "reconciled" ? now : row.synced_at,
    last_error_code: result.error_code ?? undefined, last_error: result.error ?? undefined,
    next_retry_at: state === "unknown" ? nextRetryAt(row.attempts) : undefined, updated_at: now,
  });
}
async function inquireUnknown(row: RestaurantPendingOrder): Promise<boolean> {
  try {
    const operation = (await wapApi.inquireOfflineOperation(row.client_operation_id ?? row.client_order_id)).data.data;
    const bundle = await decryptRow(row);
    await db.restaurantPendingOrders.update(row.client_order_id, {
      status: operation.status === "purged" ? "reconciled" : operation.status as RestaurantPendingOrderStatus,
      encrypted_data: await encryptOfflineValue({ ...bundle, server_order: operation.result ?? bundle.server_order }, row.client_order_id),
      server_operation_id: operation.operation_id, last_error_code: operation.error_code ?? undefined,
      last_error: operation.error ?? undefined,
      acknowledged_at: operation.acknowledged_at ? new Date(operation.acknowledged_at).getTime() : row.acknowledged_at,
      reconciled_at: operation.reconciled_at ? new Date(operation.reconciled_at).getTime() : row.reconciled_at,
      updated_at: Date.now(),
    });
    return operation.status !== "unknown";
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return false;
    throw error;
  }
}
async function purgeExpiredLocalRows(): Promise<void> {
  const cutoff = Date.now() - RETENTION_MS;
  const ids = (await db.restaurantPendingOrders.where("status").equals("reconciled").toArray())
    .filter((row) => (row.reconciled_at ?? row.synced_at ?? row.updated_at) <= cutoff)
    .map((row) => row.client_order_id);
  if (ids.length) await db.restaurantPendingOrders.bulkDelete(ids);
}
async function performRestaurantSync(brandSlug?: string): Promise<RestaurantOutboxSummary> {
  if (!await isNetworkConnected()) return getRestaurantOutboxSummary(brandSlug);
  const scope = currentScope();
  const candidates = (await db.restaurantPendingOrders.toArray())
    .filter((row) => rowMatchesScope(row, brandSlug, scope) && ACTIVE_SYNC_STATES.includes(row.status))
    .filter((row) => !row.next_retry_at || row.next_retry_at <= Date.now())
    .sort((a, b) => (a.sequence_no ?? Number.MAX_SAFE_INTEGER) - (b.sequence_no ?? Number.MAX_SAFE_INTEGER));
  for (const row of candidates) {
    try {
      if (row.status === "unknown" && await inquireUnknown(row)) continue;
      const bundle = await decryptRow(row);
      await db.restaurantPendingOrders.update(row.client_order_id, {
        status: "syncing", attempts: row.attempts + 1, last_error: undefined, updated_at: Date.now(),
      });
      const response = await wapApi.syncPaidOrders(brandSlug, [bundle.payload]);
      const result = response.data.data.results.find((item) => item.client_order_id === row.client_order_id);
      if (!result) {
        await db.restaurantPendingOrders.update(row.client_order_id, {
          status: "unknown", last_error_code: "missing_server_result",
          last_error: "เซิร์ฟเวอร์ไม่ตอบผลรายการ ต้อง inquiry ก่อนส่งซ้ำ",
          next_retry_at: nextRetryAt(row.attempts + 1), updated_at: Date.now(),
        });
      } else await applyServerResult({ ...row, attempts: row.attempts + 1 }, result);
    } catch (error) {
      if (error instanceof DOMException || (error instanceof Error && (
        error.message.includes("encryption") || error.message.includes("outbox")
      ))) {
        await quarantine(row, "outbox_integrity_failed", "ถอดรหัส Outbox ไม่สำเร็จ รายการถูกกักไว้และจะไม่ส่งอัตโนมัติ");
        continue;
      }
      const message = error instanceof Error ? error.message : "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
      await db.restaurantPendingOrders.update(row.client_order_id, {
        status: "unknown", last_error_code: "network_or_ack_unknown", last_error: message,
        attempts: row.attempts + 1, next_retry_at: nextRetryAt(row.attempts + 1), updated_at: Date.now(),
      });
      break;
    }
  }
  await purgeExpiredLocalRows();
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
  const device = useDeviceStore.getState().device;
  const clientOrderId = payload.client_order_id ?? `pos-${randomId()}`;
  const onlinePayload: WapPaidOrderPayload = { ...payload, client_order_id: clientOrderId, is_offline: false };
  if (await isNetworkConnected()) {
    try {
      const order = (await wapApi.createPaidOrder(onlinePayload, brandSlug)).data.data;
      return { order, status: "reconciled" };
    } catch (error) {
      if (axios.isAxiosError(error) && error.response) throw error;
      // Response may have been lost. Reuse the same client id in the durable outbox.
    }
  }
  if (payload.payment_method !== "cash" || (payload.payments ?? []).some((item) => item.payment_method !== "cash")) {
    throw new Error("ออฟไลน์รับได้เฉพาะเงินสด ห้ามบันทึก PromptPay หรือ Provider payment จนกว่าจะออนไลน์");
  }
  assertCurrentOfflineAuthorization(menu, scope);
  if (!device || !menu.shift_id || !menu.location_id || !menu.offline_snapshot_version) {
    throw new Error("ข้อมูล Counter, กะ, คลัง หรือ snapshot ไม่ครบ กรุณาต่ออินเทอร์เน็ตและโหลดใหม่");
  }
  const localCreatedAt = new Date().toISOString();
  const sequenceNo = await nextSequence(device.device_id, menu.shift_id);
  const queuedPayload: WapPaidOrderPayload = {
    ...payload,
    items: payload.items.map((item) => ({
      ...item, special_request: item.special_request ?? null,
      expected_unit_price: Number(menu.products.find((product) => product.id === item.product_id)?.selling_price ?? 0),
      expected_price_version: item.expected_price_version,
    })),
    payments: (payload.payments ?? []).map((payment) => ({ ...payment, reference_no: payment.reference_no ?? null })),
    shift_id: menu.shift_id, location_id: menu.location_id, client_order_id: clientOrderId,
    client_operation_id: clientOrderId, idempotency_key: `offline-sale:${device.device_id}:${clientOrderId}`,
    schema_version: "offline-pos-v1", company_id: scope.companyId, brand_id: menu.brand_id ?? null,
    branch_id: scope.branchId, station_key: device.device_code, operation_type: "cash_sale",
    sequence_no: sequenceNo, price_snapshot_version: menu.offline_snapshot_version, currency: "THB",
    local_created_at: localCreatedAt, offline_policy_version: menu.offline_policy_version,
    offline_authorization: menu.offline_authorization ?? undefined, is_offline: true,
  };
  queuedPayload.request_hash = await canonicalRequestHash(queuedPayload);
  const localOrder = buildLocalOrder(queuedPayload as WapPaidOrderPayload & { client_order_id: string; local_created_at: string }, menu, scope.userId);
  const now = Date.now();
  const row: RestaurantPendingOrder = {
    client_order_id: clientOrderId, client_operation_id: clientOrderId, company_id: scope.companyId,
    brand_id: menu.brand_id ?? null, branch_id: scope.branchId, brand_slug: normalizedBrandSlug(brandSlug),
    user_id: scope.userId, device_id: device.device_id, shift_id: menu.shift_id, station_key: device.device_code,
    schema_version: "offline-pos-v1", idempotency_key: queuedPayload.idempotency_key,
    request_hash: queuedPayload.request_hash, sequence_no: sequenceNo, operation_type: "cash_sale",
    price_snapshot_version: menu.offline_snapshot_version,
    encrypted_data: await encryptOfflineValue({ payload: queuedPayload, local_order: localOrder }, clientOrderId),
    encryption_version: 1, status: "pending_sync", attempts: 0, created_at: now, updated_at: now,
  };
  await db.restaurantPendingOrders.put(row);
  return { order: localOrder, status: "pending_sync" };
}

export async function markRestaurantLocalSlip(clientOrderId: string, type: "customer" | "kitchen"): Promise<WapOrder> {
  const row = await db.restaurantPendingOrders.get(clientOrderId);
  if (!row) throw new Error("ไม่พบออเดอร์ออฟไลน์ในเครื่อง");
  let bundle: EncryptedOrderBundle;
  try { bundle = await decryptRow(row); } catch {
    await quarantine(row, "outbox_integrity_failed", "ถอดรหัส Outbox ไม่สำเร็จ");
    throw new Error("ข้อมูล Outbox ไม่ผ่านการตรวจความถูกต้อง กรุณาให้ผู้ดูแลตรวจสอบ");
  }
  const effectiveOrder = bundle.server_order ?? bundle.local_order;
  if (type === "kitchen" && !effectiveOrder.customer_slip_printed_at) throw new Error("กรุณาพิมพ์สลิปลูกค้าก่อนส่งออเดอร์เข้าครัว");
  if (row.status === "reconciled" && bundle.server_order && await isNetworkConnected()) {
    const serverOrder = type === "customer"
      ? (await wapApi.markCustomerSlip(bundle.server_order.session_id)).data.data
      : (await wapApi.markKitchenSlip(bundle.server_order.session_id)).data.data;
    await db.restaurantPendingOrders.update(clientOrderId, {
      encrypted_data: await encryptOfflineValue({ ...bundle, server_order: serverOrder }, clientOrderId), updated_at: Date.now(),
    });
    return serverOrder;
  }
  const printedAt = new Date().toISOString();
  const localOrder = type === "customer"
    ? { ...bundle.local_order, customer_slip_printed_at: printedAt }
    : { ...bundle.local_order, kitchen_slip_printed_at: printedAt, kitchen_sent_at: printedAt };
  const updatedPayload = type === "customer"
    ? { ...bundle.payload, local_customer_slip_printed_at: printedAt }
    : { ...bundle.payload, local_kitchen_slip_printed_at: printedAt };
  await db.restaurantPendingOrders.update(clientOrderId, {
    encrypted_data: await encryptOfflineValue({ ...bundle, payload: updatedPayload, local_order: localOrder }, clientOrderId),
    status: row.status === "reconciled" ? "pending_sync" : row.status, updated_at: Date.now(),
  });
  return localOrder;
}

export async function hasUnsyncedRestaurantOrders(brandSlug?: string): Promise<boolean> {
  const summary = await getRestaurantOutboxSummary(brandSlug);
  return summary.pending + summary.syncing + summary.acknowledged + summary.needsReview + summary.quarantined + summary.unknown > 0;
}
export async function getQueuedRestaurantOrder(clientOrderId: string): Promise<WapOrder | null> {
  const row = await db.restaurantPendingOrders.get(clientOrderId);
  if (!row) return null;
  try {
    const bundle = await decryptRow(row);
    return bundle.server_order ?? bundle.local_order;
  } catch {
    await quarantine(row, "outbox_integrity_failed", "ถอดรหัส Outbox ไม่สำเร็จ");
    return null;
  }
}
export async function listRestaurantOutbox(brandSlug?: string): Promise<RestaurantPendingOrder[]> {
  const scope = currentScope();
  return (await db.restaurantPendingOrders.toArray()).filter((row) => rowMatchesScope(row, brandSlug, scope)).sort((a, b) => b.created_at - a.created_at);
}
export async function retryRestaurantNeedsReview(brandSlug?: string): Promise<RestaurantOutboxSummary> {
  const scope = currentScope();
  const rows = (await db.restaurantPendingOrders.toArray())
    .filter((row) => rowMatchesScope(row, brandSlug, scope) && row.status === "needs_review");
  await db.restaurantPendingOrders.bulkPut(rows.map((row) => ({
    ...row, status: "pending_sync" as const, last_error: undefined, last_error_code: undefined,
    next_retry_at: undefined, updated_at: Date.now(),
  })));
  return syncRestaurantPendingOrders(brandSlug);
}
export async function inquireRestaurantOperation(clientOrderId: string): Promise<void> {
  const row = await db.restaurantPendingOrders.get(clientOrderId);
  if (!row) throw new Error("ไม่พบรายการใน Outbox");
  await inquireUnknown(row);
}
