import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Ban, CheckCircle2, ChefHat, ClipboardList, CreditCard, Factory, Loader2, PackageCheck, Send, Settings2, Truck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { wapApi, type CentralOrder, type ReplenishmentPolicyPayload } from "@/lib/wapApi";

type QtyByItem = Record<string, number>;
type ReplenishmentPolicyDraft = Omit<ReplenishmentPolicyPayload, "safety_stock_percent" | "safety_stock_qty" | "pack_size" | "lead_time_days" | "minimum_order_qty"> & {
  safety_stock_percent: string;
  safety_stock_qty: string;
  pack_size: string;
  lead_time_days: string;
  minimum_order_qty: string;
};

function formatQty(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toLocaleString("th-TH", { maximumFractionDigits: 2 });
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: "ร่าง",
    submitted: "ส่งแล้ว",
    reserved_credit: "กันเครดิตแล้ว",
    approved: "อนุมัติแล้ว",
    packed: "แพ็กแล้ว",
    shipped: "จัดส่งแล้ว",
    partially_received: "สาขารับบางส่วน",
    received: "รับแล้ว",
    cancelled: "ยกเลิก",
  };
  return labels[status] ?? status;
}

function getActionQty(order: CentralOrder | null, qtyByItem: QtyByItem): Array<{ item_id: string; qty: number }> {
  return (order?.items ?? [])
    .filter((item) => item.id)
    .map((item) => ({
      item_id: item.id as string,
      qty: Math.max(Number(qtyByItem[item.id as string] ?? item.requested_qty ?? 0), 0),
    }));
}

export default function RestaurantCentralOrdersPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [cancelOrder, setCancelOrder] = useState<CentralOrder | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [shipQtyByItem, setShipQtyByItem] = useState<QtyByItem>({});
  const [centralBranchId, setCentralBranchId] = useState("");
  const [centralLocationId, setCentralLocationId] = useState("");
  const [centralReadyLocationId, setCentralReadyLocationId] = useState("");
  const [policyBranchId, setPolicyBranchId] = useState("");
  const [policyDrafts, setPolicyDrafts] = useState<Record<string, ReplenishmentPolicyDraft>>({});

  const featuresQuery = useQuery({
    queryKey: ["restaurant-brand-features", brandSlug],
    queryFn: async () => {
      if (!brandSlug) throw new Error("Brand is required");
      return (await wapApi.brandFeatures(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
  });
  const productionEnabled = !brandSlug || featuresQuery.data?.central_production === true;

  const ordersQuery = useQuery({
    queryKey: ["restaurant-central-orders", brandSlug ?? "legacy"],
    queryFn: async () => (await wapApi.centralOrders(brandSlug)).data.data,
  });
  const productionQuery = useQuery({
    queryKey: ["restaurant-central-production-summary", brandSlug ?? "legacy"],
    queryFn: async () => (await wapApi.centralProductionSummary(brandSlug)).data.data,
    enabled: productionEnabled,
  });
  const ingredientsQuery = useQuery({
    queryKey: ["restaurant-central-production-ingredients", brandSlug ?? "legacy"],
    queryFn: async () => (await wapApi.centralProductionIngredients(brandSlug)).data.data,
    enabled: productionEnabled,
  });
  const branchesQuery = useQuery({
    queryKey: ["restaurant-config-branches", brandSlug],
    queryFn: async () => (await wapApi.branches()).data.data,
    enabled: Boolean(brandSlug),
  });
  const locationsQuery = useQuery({
    queryKey: ["restaurant-config-locations", brandSlug],
    queryFn: async () => (await wapApi.stockLocations()).data.data,
    enabled: Boolean(brandSlug),
  });
  const transferConfigQuery = useQuery({
    queryKey: ["restaurant-transfer-config", brandSlug],
    queryFn: async () => {
      if (!brandSlug) return null;
      return (await wapApi.transferConfig(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
  });
  const creditAccountsQuery = useQuery({
    queryKey: ["restaurant-credit-accounts", brandSlug],
    queryFn: async () => {
      if (!brandSlug) return [];
      return (await wapApi.creditAccounts(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
  });
  const replenishmentPoliciesQuery = useQuery({
    queryKey: ["restaurant-replenishment-policies", brandSlug, policyBranchId],
    queryFn: async () => {
      if (!brandSlug || !policyBranchId) throw new Error("กรุณาเลือกสาขา");
      return (await wapApi.centralReplenishmentPolicies(brandSlug, policyBranchId)).data.data;
    },
    enabled: Boolean(brandSlug && policyBranchId),
  });
  const detailQuery = useQuery({
    queryKey: ["restaurant-central-order", brandSlug ?? "legacy", selectedOrderId],
    queryFn: async () => {
      if (!selectedOrderId) throw new Error("No selected order");
      return (await wapApi.centralOrder(selectedOrderId, brandSlug)).data.data;
    },
    enabled: Boolean(selectedOrderId),
  });
  const storeBase = brandSlug ? `/store/${brandSlug}` : "/restaurant";
  const centralBase = brandSlug ? `/central/${brandSlug}` : "/restaurant";

  const selectedOrder = detailQuery.data ?? null;
  const isLoading = ordersQuery.isLoading
    || featuresQuery.isLoading
    || (productionEnabled && (productionQuery.isLoading || ingredientsQuery.isLoading));
  const isWorking = useMemo(
    () => detailQuery.isFetching,
    [detailQuery.isFetching]
  );

  useEffect(() => {
    if (!selectedOrder?.items) return;
    setShipQtyByItem(Object.fromEntries(
      selectedOrder.items
        .filter((item) => item.id)
        .map((item) => [
          item.id as string,
          Number(item.shipped_qty && item.shipped_qty > 0 ? item.shipped_qty : item.approved_qty || item.requested_qty || 0),
        ])
    ));
  }, [selectedOrder]);

  useEffect(() => {
    const config = transferConfigQuery.data;
    if (!config) return;
    setCentralBranchId(config.central_branch_id ?? "");
    setCentralLocationId(config.central_location_id ?? "");
    setCentralReadyLocationId(config.central_ready_location_id ?? "");
  }, [transferConfigQuery.data]);

  useEffect(() => {
    if (policyBranchId || !creditAccountsQuery.data?.length) return;
    setPolicyBranchId(creditAccountsQuery.data[0].branch_id);
  }, [creditAccountsQuery.data, policyBranchId]);

  useEffect(() => {
    const items = replenishmentPoliciesQuery.data?.items ?? [];
    setPolicyDrafts(Object.fromEntries(items.map((item) => [
      item.product_id,
      {
        is_enabled: item.is_enabled,
        safety_stock_percent: String(item.safety_stock_percent),
        safety_stock_qty: String(item.fixed_safety_stock_qty),
        pack_size: String(item.pack_size),
        lead_time_days: String(item.lead_time_days),
        forecast_method: item.configured_forecast_method === "latest_day" || item.configured_forecast_method === "average_7_open_days"
          ? item.configured_forecast_method
          : "auto",
        minimum_order_qty: String(item.minimum_order_qty),
      },
    ])));
  }, [replenishmentPoliciesQuery.data?.items]);

  async function refreshCentral(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["restaurant-central-orders", brandSlug ?? "legacy"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-central-production-summary", brandSlug ?? "legacy"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-central-production-ingredients", brandSlug ?? "legacy"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-central-order", brandSlug ?? "legacy", selectedOrderId] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-transfer-config", brandSlug] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-replenishment-policies", brandSlug, policyBranchId] }),
    ]);
  }

  const approveMutation = useMutation({
    mutationFn: async (order: CentralOrder) =>
      (await wapApi.approveCentralOrder(order.id, { items: getActionQty(order, shipQtyByItem) })).data.data,
    onSuccess: async (order) => {
      toast({ title: `อนุมัติแล้ว: ${order.order_number}` });
      await refreshCentral();
    },
    onError: (error) => toast({ title: "อนุมัติไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });

  const packMutation = useMutation({
    mutationFn: async (order: CentralOrder) =>
      (await wapApi.packCentralOrder(order.id, { items: getActionQty(order, shipQtyByItem) })).data.data,
    onSuccess: async (order) => {
      toast({ title: `แพ็กสินค้าแล้ว: ${order.order_number}` });
      await refreshCentral();
    },
    onError: (error) => toast({ title: "แพ็กสินค้าไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });

  const shipMutation = useMutation({
    mutationFn: async (order: CentralOrder) => (await wapApi.shipCentralOrder(order.id)).data.data,
    onSuccess: async (order) => {
      toast({ title: `จัดส่งแล้ว: ${order.order_number}` });
      await refreshCentral();
    },
    onError: (error) => toast({ title: "จัดส่งไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });
  const cancelMutation = useMutation({
    mutationFn: async (order: CentralOrder) => {
      if (!cancelReason.trim()) throw new Error("กรุณาระบุเหตุผลการยกเลิก");
      return (await wapApi.cancelCentralOrder(order.id, cancelReason.trim())).data.data;
    },
    onSuccess: async (order) => {
      toast({ title: `ยกเลิกแล้ว: ${order.order_number}` });
      setCancelOrder(null);
      setCancelReason("");
      await refreshCentral();
    },
    onError: (error) => toast({ title: "ยกเลิกไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });
  const transferConfigMutation = useMutation({
    mutationFn: async () => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return (await wapApi.updateTransferConfig(brandSlug, {
        central_branch_id: centralBranchId || null,
        central_location_id: centralLocationId || null,
        central_ready_location_id: centralReadyLocationId || null,
      })).data.data;
    },
    onSuccess: async () => {
      toast({ title: "บันทึกคลังกลางแล้ว" });
      await refreshCentral();
    },
    onError: (error) => toast({ title: "บันทึกคลังกลางไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });
  const replenishmentPolicyMutation = useMutation({
    mutationFn: async ({ productId, draft }: { productId: string; draft: ReplenishmentPolicyDraft }) => {
      if (!brandSlug || !policyBranchId) throw new Error("กรุณาเลือกสาขา");
      const payload: ReplenishmentPolicyPayload = {
        is_enabled: draft.is_enabled,
        safety_stock_percent: Math.max(Number(draft.safety_stock_percent || 0), 0),
        safety_stock_qty: Math.max(Number(draft.safety_stock_qty || 0), 0),
        pack_size: Math.max(Number(draft.pack_size || 1), 0.0001),
        lead_time_days: Math.max(Math.round(Number(draft.lead_time_days || 1)), 1),
        forecast_method: draft.forecast_method,
        minimum_order_qty: Math.max(Number(draft.minimum_order_qty || 0), 0),
      };
      return (await wapApi.updateReplenishmentPolicy(brandSlug, policyBranchId, productId, payload)).data.data;
    },
    onSuccess: async () => {
      toast({ title: "บันทึกนโยบายสั่งสินค้าแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["restaurant-replenishment-policies", brandSlug, policyBranchId] });
    },
    onError: (error) => toast({ title: "บันทึกนโยบายไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });

  function updatePolicyDraft(productId: string, patch: Partial<ReplenishmentPolicyDraft>): void {
    setPolicyDrafts((previous) => ({
      ...previous,
      [productId]: { ...previous[productId], ...patch },
    }));
  }
  const centralLocations = (locationsQuery.data ?? []).filter((location) => !centralBranchId || location.branch_id === centralBranchId);

  return (
    <div className="mx-auto flex min-h-full max-w-5xl flex-col gap-4">
      <header className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 p-4">
          <div className="flex min-w-0 items-center gap-3">
            <Button asChild variant="outline" size="icon" className="h-10 w-10 shrink-0">
              <Link to={`${storeBase}/orders`} aria-label="กลับหน้ารับออเดอร์">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-black text-slate-950">ร้านอาหาร ส่วนกลาง</h1>
              <p className="truncate text-sm text-slate-500">ใบสั่งสินค้าจากสาขาและยอดรวมผลิต</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {productionEnabled ? (
              <Button asChild variant="outline" size="sm">
                <Link to={`${centralBase}/production`}>
                  <Factory className="mr-2 h-4 w-4" />
                  ผลิต
                </Link>
              </Button>
            ) : null}
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/credits`}>
                <CreditCard className="mr-2 h-4 w-4" />
                เครดิต
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/recipes`}>
                <ChefHat className="mr-2 h-4 w-4" />
                สูตร
              </Link>
            </Button>
            <span className="hidden rounded-full bg-slate-100 px-3 py-1.5 text-sm font-semibold text-slate-700 sm:inline-flex">
              {ordersQuery.data?.length ?? 0} ใบสั่ง
            </span>
          </div>
        </div>
      </header>

      {isLoading ? (
        <div className="flex h-72 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          โหลดข้อมูลครัวกลาง
        </div>
      ) : ordersQuery.isError
        || featuresQuery.isError
        || (productionEnabled && (productionQuery.isError || ingredientsQuery.isError)) ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-center font-semibold text-rose-700">
          โหลดข้อมูลครัวกลางไม่สำเร็จ
        </div>
      ) : (
        <>
          {productionEnabled ? <>
          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4">
              <PackageCheck className="h-5 w-5 text-orange-600" />
              <h2 className="font-bold text-slate-950">รวมยอดผลิต</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {(productionQuery.data ?? []).length > 0 ? productionQuery.data?.map((item) => (
                <div key={`${item.product_id ?? item.sku}:${item.unit}`} className="grid grid-cols-[1fr_auto] gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <p className="font-bold text-slate-950">{item.product_name}</p>
                    <p className="text-sm text-slate-500">{item.order_count} ใบสั่ง</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xl font-black text-orange-700">{formatQty(item.requested_qty)}</p>
                    <p className="text-xs text-slate-500">{item.unit}</p>
                  </div>
                </div>
              )) : (
                <div className="p-8 text-center text-slate-500">ยังไม่มียอดผลิตที่รอจัดการ</div>
              )}
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4">
              <PackageCheck className="h-5 w-5 text-emerald-700" />
              <h2 className="font-bold text-slate-950">รวมวัตถุดิบที่ต้องเตรียม</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {(ingredientsQuery.data ?? []).length > 0 ? ingredientsQuery.data?.map((item) => (
                <div key={`${item.product_id ?? item.sku}:${item.unit}`} className="grid grid-cols-[1fr_auto] gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <p className="font-bold text-slate-950">{item.product_name}</p>
                    <p className="text-sm text-slate-500">
                      {item.sku || "-"} · {item.order_count} ใบสั่ง
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xl font-black text-emerald-700">{formatQty(item.required_qty)}</p>
                    <p className="text-xs text-slate-500">{item.unit}</p>
                  </div>
                </div>
              )) : (
                <div className="p-8 text-center text-slate-500">ยังไม่มีวัตถุดิบที่ต้องเตรียม</div>
              )}
            </div>
          </section>
          </> : null}

          {brandSlug ? (
            <section className="rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center gap-2 border-b border-slate-200 p-4">
                <Truck className="h-5 w-5 text-slate-700" />
                <h2 className="font-bold text-slate-950">ตั้งค่าคลังสำหรับ Transfer</h2>
              </div>
              <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_auto] xl:items-end">
                <div>
                  <p className="mb-1 text-sm font-semibold text-slate-600">สาขาครัวกลาง</p>
                  <select
                    className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                    value={centralBranchId}
                    onChange={(event) => {
                      setCentralBranchId(event.target.value);
                      setCentralLocationId("");
                      setCentralReadyLocationId("");
                    }}
                  >
                    <option value="">เลือกสาขา</option>
                    {(branchesQuery.data ?? []).map((branch) => (
                      <option key={branch.id} value={branch.id}>{branch.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <p className="mb-1 text-sm font-semibold text-slate-600">คลังวัตถุดิบ (RAW)</p>
                  <select
                    className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                    value={centralLocationId}
                    onChange={(event) => setCentralLocationId(event.target.value)}
                  >
                    <option value="">เลือกคลัง</option>
                    {centralLocations.map((location) => (
                      <option key={location.id} value={location.id}>{location.name} ({location.code})</option>
                    ))}
                  </select>
                </div>
                <div>
                  <p className="mb-1 text-sm font-semibold text-slate-600">คลังพร้อมส่ง (READY)</p>
                  <select
                    className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                    value={centralReadyLocationId}
                    onChange={(event) => setCentralReadyLocationId(event.target.value)}
                  >
                    <option value="">เลือกคลัง</option>
                    {centralLocations.map((location) => (
                      <option
                        key={location.id}
                        value={location.id}
                        disabled={location.id === centralLocationId}
                      >
                        {location.name} ({location.code})
                      </option>
                    ))}
                  </select>
                </div>
                <Button
                  className="h-10 bg-slate-950 hover:bg-slate-800"
                  disabled={
                    transferConfigMutation.isPending
                    || !centralBranchId
                    || !centralLocationId
                    || !centralReadyLocationId
                    || centralLocationId === centralReadyLocationId
                  }
                  onClick={() => transferConfigMutation.mutate()}
                >
                  {transferConfigMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
                  บันทึก
                </Button>
              </div>
            </section>
          ) : null}

          {brandSlug ? (
            <section className="rounded-lg border border-slate-200 bg-white">
              <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                  <Settings2 className="h-5 w-5 text-blue-700" />
                  <div>
                    <h2 className="font-bold text-slate-950">นโยบายแนะนำสั่งวันถัดไป</h2>
                    <p className="text-sm text-slate-500">กำหนด Safety stock, ขนาดแพ็ก และวิธี Forecast แยกตามสาขา</p>
                  </div>
                </div>
                <select
                  className="h-10 min-w-56 rounded-md border border-gray-300 px-3 text-sm"
                  value={policyBranchId}
                  onChange={(event) => setPolicyBranchId(event.target.value)}
                >
                  <option value="">เลือกสาขา</option>
                  {(creditAccountsQuery.data ?? []).map((account) => (
                    <option key={account.branch_id} value={account.branch_id}>{account.branch_name ?? account.branch_id}</option>
                  ))}
                </select>
              </div>
              {!policyBranchId ? (
                <div className="p-8 text-center text-slate-500">เลือกสาขาเพื่อกำหนดนโยบาย</div>
              ) : replenishmentPoliciesQuery.isLoading ? (
                <div className="flex h-32 items-center justify-center text-slate-500">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  โหลดนโยบายสั่งสินค้า
                </div>
              ) : replenishmentPoliciesQuery.isError ? (
                <div className="border-t border-amber-200 bg-amber-50 p-6 text-center font-semibold text-amber-800">
                  โหลดนโยบายไม่ได้ กรุณาตรวจว่าได้ตั้งคลัง STORE-STOCK ให้สาขานี้แล้ว
                </div>
              ) : (replenishmentPoliciesQuery.data?.items ?? []).length === 0 ? (
                <div className="p-8 text-center text-slate-500">ยังไม่มีสินค้า READY ในสูตรหน้าร้านของสาขานี้</div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {replenishmentPoliciesQuery.data?.items.map((item) => {
                    const draft = policyDrafts[item.product_id];
                    if (!draft) return null;
                    return (
                      <div key={item.product_id} className="space-y-3 p-4">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                          <div>
                            <p className="font-bold text-slate-950">{item.product_name}</p>
                            <p className="text-sm text-slate-500">
                              {item.sku} · คงเหลือ {formatQty(item.store_on_hand_qty)} {item.unit} · ระบบแนะนำ {formatQty(item.suggested_qty)} {item.unit}
                            </p>
                          </div>
                          <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                            <input
                              type="checkbox"
                              checked={draft.is_enabled}
                              onChange={(event) => updatePolicyDraft(item.product_id, { is_enabled: event.target.checked })}
                            />
                            เปิดแนะนำสินค้า
                          </label>
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-7 xl:items-end">
                          <label className="text-xs font-semibold text-slate-600">
                            Safety %
                            <Input className="mt-1" type="number" min="0" step="0.1" value={draft.safety_stock_percent} onChange={(event) => updatePolicyDraft(item.product_id, { safety_stock_percent: event.target.value })} />
                          </label>
                          <label className="text-xs font-semibold text-slate-600">
                            Safety คงที่
                            <Input className="mt-1" type="number" min="0" step="0.01" value={draft.safety_stock_qty} onChange={(event) => updatePolicyDraft(item.product_id, { safety_stock_qty: event.target.value })} />
                          </label>
                          <label className="text-xs font-semibold text-slate-600">
                            ขนาดแพ็ก
                            <Input className="mt-1" type="number" min="0.0001" step="0.01" value={draft.pack_size} onChange={(event) => updatePolicyDraft(item.product_id, { pack_size: event.target.value })} />
                          </label>
                          <label className="text-xs font-semibold text-slate-600">
                            ขั้นต่ำ
                            <Input className="mt-1" type="number" min="0" step="0.01" value={draft.minimum_order_qty} onChange={(event) => updatePolicyDraft(item.product_id, { minimum_order_qty: event.target.value })} />
                          </label>
                          <label className="text-xs font-semibold text-slate-600">
                            Lead time (วัน)
                            <Input className="mt-1" type="number" min="1" step="1" value={draft.lead_time_days} onChange={(event) => updatePolicyDraft(item.product_id, { lead_time_days: event.target.value })} />
                          </label>
                          <label className="text-xs font-semibold text-slate-600">
                            Forecast
                            <select
                              className="mt-1 h-10 w-full rounded-md border border-gray-300 px-2 text-sm font-normal"
                              value={draft.forecast_method}
                              onChange={(event) => updatePolicyDraft(item.product_id, { forecast_method: event.target.value as ReplenishmentPolicyDraft["forecast_method"] })}
                            >
                              <option value="auto">อัตโนมัติ</option>
                              <option value="latest_day">วันล่าสุด</option>
                              <option value="average_7_open_days">เฉลี่ย 7 วันเปิด</option>
                            </select>
                          </label>
                          <Button
                            className="h-10 bg-blue-700 hover:bg-blue-800"
                            disabled={replenishmentPolicyMutation.isPending}
                            onClick={() => replenishmentPolicyMutation.mutate({ productId: item.product_id, draft })}
                          >
                            {replenishmentPolicyMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
                            บันทึก
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          ) : null}

          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center gap-2 border-b border-slate-200 p-4">
              <ClipboardList className="h-5 w-5 text-slate-700" />
              <h2 className="font-bold text-slate-950">ใบสั่งจากสาขา</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {(ordersQuery.data ?? []).length > 0 ? ordersQuery.data?.map((order) => (
                <button
                  key={order.id}
                  type="button"
                  className="grid w-full gap-2 px-4 py-3 text-left transition hover:bg-slate-50 sm:grid-cols-[1fr_auto] sm:items-center"
                  onClick={() => setSelectedOrderId(order.id)}
                >
                  <div className="min-w-0">
                    <p className="font-bold text-slate-950">{order.order_number}</p>
                    <p className="text-sm text-slate-500">
                      {order.branch_name ?? "ไม่ระบุสาขา"} · {formatDateTime(order.submitted_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 sm:justify-end">
                    <span className="rounded-full bg-orange-100 px-3 py-1 text-sm font-bold text-orange-700">
                      {statusLabel(order.status)}
                    </span>
                    <span className="text-sm font-semibold text-slate-500">{order.item_count ?? 0} รายการ</span>
                  </div>
                </button>
              )) : (
                <div className="p-8 text-center text-slate-500">ยังไม่มีใบสั่งจากสาขา</div>
              )}
            </div>
          </section>
        </>
      )}

      <Dialog open={Boolean(selectedOrderId)} onOpenChange={(open) => !open && setSelectedOrderId(null)}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-auto">
          <DialogHeader>
            <DialogTitle>{selectedOrder?.order_number ?? "ใบสั่งสินค้า"}</DialogTitle>
            <DialogDescription>
              {selectedOrder ? `${selectedOrder.branch_name ?? "ไม่ระบุสาขา"} · ${statusLabel(selectedOrder.status)}` : "โหลดรายละเอียด"}
            </DialogDescription>
          </DialogHeader>

          {isWorking || !selectedOrder ? (
            <div className="flex h-48 items-center justify-center text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              โหลดใบสั่งสินค้า
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid gap-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-600 sm:grid-cols-4">
                <div>
                  <p className="font-semibold text-slate-500">ส่งจากสาขา</p>
                  <p className="font-bold text-slate-900">{formatDateTime(selectedOrder.submitted_at)}</p>
                </div>
                <div>
                  <p className="font-semibold text-slate-500">อนุมัติ</p>
                  <p className="font-bold text-slate-900">{formatDateTime(selectedOrder.approved_at)}</p>
                </div>
                <div>
                  <p className="font-semibold text-slate-500">แพ็ก</p>
                  <p className="font-bold text-slate-900">{formatDateTime(selectedOrder.packed_at)}</p>
                </div>
                <div>
                  <p className="font-semibold text-slate-500">Transfer</p>
                  <p className="font-bold text-slate-900">
                    {selectedOrder.transfer_order_number ?? (selectedOrder.transfer_order_id ? "สร้างแล้ว" : "ยังไม่สร้าง")}
                  </p>
                  {selectedOrder.transfer_order_status ? (
                    <p className="text-xs text-slate-500">{selectedOrder.transfer_order_status}</p>
                  ) : null}
                </div>
              </div>
              {selectedOrder.items?.map((item) => (
                <div key={item.id ?? item.sku} className="rounded-lg border border-slate-200 p-3">
                  <div className="grid gap-3 sm:grid-cols-[1fr_110px_110px_110px_140px] sm:items-center">
                    <div className="min-w-0">
                      <p className="font-bold text-slate-950">{item.product_name}</p>
                      <p className="text-sm text-slate-500">{item.sku}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-500">ระบบแนะนำ</p>
                      <p className="font-black text-blue-700">{formatQty(item.system_qty)} {item.unit}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-500">สาขาสั่ง</p>
                      <p className="font-black text-slate-950">{formatQty(item.requested_qty)} {item.unit}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-500">อนุมัติ</p>
                      <p className="font-black text-slate-950">{formatQty(item.approved_qty || item.requested_qty)} {item.unit}</p>
                    </div>
                    <div>
                      <p className="mb-1 text-xs font-semibold text-slate-500">ส่งจริง</p>
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        value={shipQtyByItem[item.id ?? ""] ?? 0}
                        disabled={!["submitted", "reserved_credit", "approved"].includes(selectedOrder.status)}
                        onChange={(event) => {
                          if (!item.id) return;
                          setShipQtyByItem((prev) => ({ ...prev, [item.id as string]: Number(event.target.value) }));
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedOrderId(null)}>ปิด</Button>
            {selectedOrder && ["submitted", "reserved_credit", "approved", "packed"].includes(selectedOrder.status) ? (
              <Button
                variant="outline"
                className="border-red-200 text-red-600 hover:bg-red-50"
                disabled={cancelMutation.isPending}
                onClick={() => {
                  setCancelOrder(selectedOrder);
                  setCancelReason("");
                }}
              >
                {cancelMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Ban className="mr-2 h-4 w-4" />}
                ยกเลิก
              </Button>
            ) : null}
            {selectedOrder?.status === "submitted" || selectedOrder?.status === "reserved_credit" ? (
              <Button
                className="bg-emerald-600 hover:bg-emerald-700"
                disabled={approveMutation.isPending}
                onClick={() => approveMutation.mutate(selectedOrder)}
              >
                {approveMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
                อนุมัติ
              </Button>
            ) : null}
            {selectedOrder?.status === "approved" ? (
              <Button
                className="bg-orange-600 hover:bg-orange-700"
                disabled={packMutation.isPending}
                onClick={() => packMutation.mutate(selectedOrder)}
              >
                {packMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PackageCheck className="mr-2 h-4 w-4" />}
                แพ็กสินค้า
              </Button>
            ) : null}
            {selectedOrder?.status === "packed" ? (
              <Button
                className="bg-slate-950 hover:bg-slate-800"
                disabled={shipMutation.isPending}
                onClick={() => shipMutation.mutate(selectedOrder)}
              >
                {shipMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Truck className="mr-2 h-4 w-4" />}
                จัดส่ง
              </Button>
            ) : null}
            {selectedOrder?.status === "shipped" ? (
              <Button disabled>
                <Send className="mr-2 h-4 w-4" />
                รอสาขารับของ
              </Button>
            ) : null}
            {selectedOrder?.status === "partially_received" ? (
              <Button disabled>
                <Send className="mr-2 h-4 w-4" />
                สาขารับบางส่วน
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(cancelOrder)} onOpenChange={(open) => {
        if (!open) {
          setCancelOrder(null);
          setCancelReason("");
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>ยกเลิกใบสั่งสินค้า</DialogTitle>
            <DialogDescription>{cancelOrder?.order_number ?? ""}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-600">เหตุผล</p>
            <Input
              value={cancelReason}
              onChange={(event) => setCancelReason(event.target.value)}
              placeholder="เช่น สาขาขอยกเลิก หรือรายการผิด"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOrder(null)}>ปิด</Button>
            <Button
              className="bg-red-600 hover:bg-red-700"
              disabled={!cancelReason.trim() || cancelMutation.isPending || !cancelOrder}
              onClick={() => cancelOrder && cancelMutation.mutate(cancelOrder)}
            >
              {cancelMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Ban className="mr-2 h-4 w-4" />}
              ยืนยันยกเลิก
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  );
}
