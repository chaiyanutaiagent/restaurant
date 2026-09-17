import axios from "axios";
import { Network } from "@capacitor/network";
import {
  db,
  type TakeawayLocalOrder,
  type TakeawayPendingSale,
  type TakeawayWorkspaceSnapshot,
} from "@/lib/db";
import {
  takeawayApi,
  type TakeawayCatalogRow,
  type TakeawayReceipt,
  type TakeawaySalePayload,
} from "@/lib/takeawayApi";
import { useAuthStore } from "@/stores/auth.store";

type TakeawayScope = {
  companyId: string;
  brandId: string;
  branchId: string;
  userId: string;
};

export type TakeawayOutboxSummary = {
  pending: number;
  syncing: number;
  needsReview: number;
  latestError?: string;
};

export type TakeawayQueuedSaleResult = {
  clientSaleId: string;
  order: TakeawayLocalOrder | (Record<string, unknown> & { id: string });
  receipt: TakeawayReceipt;
  pickupToken: string | null;
  status: TakeawayPendingSale["status"];
  error?: string;
};

const activeSyncs = new Map<string, Promise<TakeawayOutboxSummary>>();

function currentScope(): TakeawayScope {
  const { companyId, brandId, branchId, user } = useAuthStore.getState();
  if (!companyId || !brandId || !branchId || !user?.id) {
    throw new Error("กรุณาเข้าสู่ระบบและเลือกสาขา Takeaway ก่อนขาย");
  }
  return { companyId, brandId, branchId, userId: user.id };
}

function scopeKey(scope = currentScope()): string {
  return `${scope.companyId}:${scope.brandId}:${scope.branchId}:${scope.userId}`;
}

function randomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function isConnected(): Promise<boolean> {
  if (typeof navigator !== "undefined" && !navigator.onLine) return false;
  try {
    const browserFallback = typeof navigator === "undefined" || navigator.onLine;
    return await Promise.race([
      Network.getStatus().then((status) => status.connected),
      new Promise<boolean>((resolve) => globalThis.setTimeout(() => resolve(browserFallback), 500)),
    ]);
  } catch {
    return typeof navigator === "undefined" || navigator.onLine;
  }
}

async function installationId(): Promise<string> {
  const key = "takeaway.installation_id";
  const existing = await db.offlineSettings.get(key);
  if (existing?.value) return existing.value;
  const value = randomId();
  await db.offlineSettings.put({ key, value });
  return value;
}

async function nextSequence(scope: TakeawayScope): Promise<number> {
  const key = `takeaway.sequence:${scope.companyId}:${scope.branchId}`;
  return db.transaction("rw", db.offlineSettings, async () => {
    const previous = Number((await db.offlineSettings.get(key))?.value ?? 0);
    const next = Number.isSafeInteger(previous) && previous >= 0 ? previous + 1 : 1;
    await db.offlineSettings.put({ key, value: String(next) });
    return next;
  });
}

export async function refreshTakeawayWorkspace(): Promise<TakeawayWorkspaceSnapshot> {
  const scope = currentScope();
  const context = (await takeawayApi.status()).data.data;
  if (context.brand_id !== scope.brandId || context.branch_id !== scope.branchId) {
    throw new Error("บริบท Takeaway ของเซิร์ฟเวอร์ไม่ตรงกับสาขาที่เลือก");
  }
  const [categories, catalog, shifts] = await Promise.all([
    takeawayApi.categories(scope.brandId),
    takeawayApi.catalog(scope.brandId, scope.branchId),
    takeawayApi.shifts(),
  ]);
  const snapshot: TakeawayWorkspaceSnapshot = {
    key: scopeKey(scope),
    company_id: scope.companyId,
    brand_id: scope.brandId,
    branch_id: scope.branchId,
    user_id: scope.userId,
    context,
    categories: categories.data.data,
    catalog: catalog.data.data,
    shifts: shifts.data.data,
    synced_at: Date.now(),
  };
  await db.takeawayWorkspaceSnapshots.put(snapshot);
  return snapshot;
}

export async function loadTakeawayWorkspace(): Promise<TakeawayWorkspaceSnapshot> {
  if (await isConnected()) {
    try {
      return await refreshTakeawayWorkspace();
    } catch {
      // The browser can report online before the API is reachable; use the last safe snapshot.
    }
  }
  const cached = await db.takeawayWorkspaceSnapshots.get(scopeKey());
  if (!cached) {
    throw new Error("ยังไม่มีเมนู Takeaway ในเครื่อง กรุณาต่ออินเทอร์เน็ตและเปิดหน้าขายหนึ่งครั้ง");
  }
  return cached;
}

function rowMatchesScope(row: TakeawayPendingSale, scope: TakeawayScope): boolean {
  return row.company_id === scope.companyId
    && row.brand_id === scope.brandId
    && row.branch_id === scope.branchId
    && row.user_id === scope.userId;
}

export async function getTakeawayOutboxSummary(): Promise<TakeawayOutboxSummary> {
  const scope = currentScope();
  const rows = (await db.takeawayPendingSales.toArray()).filter((row) => rowMatchesScope(row, scope));
  return {
    pending: rows.filter((row) => row.status === "pending").length,
    syncing: rows.filter((row) => row.status === "syncing").length,
    needsReview: rows.filter((row) => row.status === "needs_review").length,
    latestError: rows
      .filter((row) => row.status === "needs_review" && row.last_error)
      .sort((a, b) => b.updated_at - a.updated_at)[0]?.last_error,
  };
}

function localArtifacts(
  clientSaleId: string,
  payload: TakeawaySalePayload,
  catalog: TakeawayCatalogRow[],
): { order: TakeawayLocalOrder; receipt: TakeawayReceipt } {
  const itemsById = new Map(catalog.map((row) => [row.item.id, row]));
  const suffix = clientSaleId.replace(/[^a-zA-Z0-9]/g, "").slice(-6).toUpperCase();
  const createdAt = new Date().toISOString();
  let subtotal = 0;
  let tax = 0;
  const receiptLines = payload.items.map((line) => {
    const row = itemsById.get(line.catalog_item_id);
    const price = Number(row?.effective_price ?? 0);
    const taxRate = Number(row?.item.tax_rate ?? 0);
    const lineSubtotal = price * Number(line.quantity);
    const lineTax = lineSubtotal * taxRate / 100;
    subtotal += lineSubtotal;
    tax += lineTax;
    return {
      sku: String(row?.item.sku ?? "OFFLINE"),
      name: String(row?.item.name ?? "สินค้าออฟไลน์"),
      quantity: line.quantity,
      line_total: (lineSubtotal + lineTax).toFixed(2),
    };
  });
  const localOrder: TakeawayLocalOrder = {
    id: `local:${clientSaleId}`,
    order_number: `OFFLINE-${suffix}`,
    queue_number: null,
    total_amount: payload.payment.amount,
    status: "offline_pending",
    fulfillment_status: "offline_pending",
    created_at: createdAt,
  };
  const localReceipt: TakeawayReceipt = {
    id: `local-receipt:${clientSaleId}`,
    order_id: localOrder.id,
    receipt_number: `LOCAL-${suffix}`,
    payload: {
      order_number: localOrder.order_number,
      queue_number: null,
      items: receiptLines,
      subtotal: subtotal.toFixed(2),
      discount_amount: payload.discount_amount,
      tax_amount: tax.toFixed(2),
      total_amount: payload.payment.amount,
      payment_method: payload.payment.method,
    },
    issued_at: createdAt,
    print_count: 0,
    last_printed_at: null,
    last_printed_copy: null,
  };
  return { order: localOrder, receipt: localReceipt };
}

async function performSync(): Promise<TakeawayOutboxSummary> {
  if (!await isConnected()) return getTakeawayOutboxSummary();
  const scope = currentScope();
  const rows = (await db.takeawayPendingSales.toArray())
    .filter((row) => rowMatchesScope(row, scope))
    .filter((row) => row.status === "pending" || row.status === "syncing")
    .sort((a, b) => a.created_at - b.created_at);

  for (const row of rows) {
    await db.takeawayPendingSales.update(row.client_sale_id, {
      status: "syncing",
      attempts: row.attempts + 1,
      updated_at: Date.now(),
    });
    try {
      const response = await takeawayApi.createSale(row.payload, true);
      const serverOrder = response.data.data.order;
      let serverReceipt: TakeawayReceipt | undefined;
      try {
        serverReceipt = (await takeawayApi.receipt(serverOrder.id)).data.data;
      } catch {
        // The sale is already durable. Receipt can be fetched again from recent orders.
      }
      await db.takeawayPendingSales.update(row.client_sale_id, {
        status: "synced",
        server_order: serverOrder,
        server_receipt: serverReceipt,
        pickup_token: response.data.data.pickup_token,
        last_error: undefined,
        synced_at: Date.now(),
        updated_at: Date.now(),
      });
    } catch (error) {
      const hasServerResponse = axios.isAxiosError(error) && Boolean(error.response);
      await db.takeawayPendingSales.update(row.client_sale_id, {
        status: hasServerResponse ? "needs_review" : "pending",
        last_error: error instanceof Error ? error.message : "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ",
        updated_at: Date.now(),
      });
      if (!hasServerResponse) break;
    }
  }
  return getTakeawayOutboxSummary();
}

export function syncTakeawayPendingSales(): Promise<TakeawayOutboxSummary> {
  const key = scopeKey();
  const active = activeSyncs.get(key);
  if (active) return active;
  const promise = performSync().finally(() => activeSyncs.delete(key));
  activeSyncs.set(key, promise);
  return promise;
}

export async function retryTakeawayNeedsReview(): Promise<TakeawayOutboxSummary> {
  const scope = currentScope();
  const rows = (await db.takeawayPendingSales.toArray())
    .filter((row) => rowMatchesScope(row, scope) && row.status === "needs_review");
  await db.takeawayPendingSales.bulkPut(rows.map((row) => ({
    ...row,
    status: "pending" as const,
    last_error: undefined,
    updated_at: Date.now(),
  })));
  return syncTakeawayPendingSales();
}

export async function queueTakeawaySale(
  draft: Omit<TakeawaySalePayload, "idempotency_key" | "offline_device_id" | "offline_sequence" | "payment"> & {
    payment: Omit<TakeawaySalePayload["payment"], "idempotency_key">;
  },
  catalog: TakeawayCatalogRow[],
): Promise<TakeawayQueuedSaleResult> {
  const scope = currentScope();
  const deviceId = await installationId();
  const sequence = await nextSequence(scope);
  const clientSaleId = `${deviceId}:${sequence}`;
  const payload: TakeawaySalePayload = {
    ...draft,
    idempotency_key: `takeaway-sale:${clientSaleId}`,
    offline_device_id: deviceId,
    offline_sequence: sequence,
    payment: {
      ...draft.payment,
      idempotency_key: `takeaway-payment:${clientSaleId}`,
    },
  };
  const { order, receipt } = localArtifacts(clientSaleId, payload, catalog);
  const now = Date.now();
  await db.takeawayPendingSales.put({
    client_sale_id: clientSaleId,
    company_id: scope.companyId,
    brand_id: scope.brandId,
    branch_id: scope.branchId,
    user_id: scope.userId,
    payload,
    local_order: order,
    local_receipt: receipt,
    status: "pending",
    attempts: 0,
    created_at: now,
    updated_at: now,
  });
  if (await isConnected()) await syncTakeawayPendingSales();
  const saved = await db.takeawayPendingSales.get(clientSaleId);
  return {
    clientSaleId,
    order: saved?.server_order ?? saved?.local_order ?? order,
    receipt: saved?.server_receipt ?? saved?.local_receipt ?? receipt,
    pickupToken: saved?.pickup_token ?? null,
    status: saved?.status ?? "pending",
    error: saved?.last_error,
  };
}

export async function markTakeawayReceiptPrinted(
  clientSaleId: string | null,
  orderId: string,
  copyType: "customer" | "merchant",
): Promise<TakeawayReceipt> {
  const printedAt = new Date().toISOString();
  if (clientSaleId) {
    const row = await db.takeawayPendingSales.get(clientSaleId);
    if (row) {
      const current = row.server_receipt ?? row.local_receipt;
      const localReceipt = {
        ...current,
        print_count: Number(current.print_count ?? 0) + 1,
        last_printed_at: printedAt,
        last_printed_copy: copyType,
      };
      await db.takeawayPendingSales.update(clientSaleId, {
        ...(row.server_receipt ? { server_receipt: localReceipt } : { local_receipt: localReceipt }),
        updated_at: Date.now(),
      });
      if (row.status !== "synced" || orderId.startsWith("local:")) return localReceipt;
    }
  }
  return (
    await takeawayApi.markReceiptPrinted(
      orderId,
      copyType,
      `takeaway-print:${copyType}:${randomId()}`,
    )
  ).data.data;
}

export async function hasUnsyncedTakeawaySales(): Promise<boolean> {
  const summary = await getTakeawayOutboxSummary();
  return summary.pending + summary.syncing + summary.needsReview > 0;
}
