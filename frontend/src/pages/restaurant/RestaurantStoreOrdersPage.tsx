import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2, ClipboardList, CreditCard, Loader2, PackageOpen, Truck } from "lucide-react";
import { useState } from "react";
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
import { wapApi, type CentralOrder } from "@/lib/wapApi";

function formatQty(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toLocaleString("th-TH", { maximumFractionDigits: 2 });
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

function formatMoney(value: number | null | undefined): string {
  return `฿${(value ?? 0).toLocaleString("th-TH", { maximumFractionDigits: 2 })}`;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    submitted: "ส่งแล้ว",
    reserved_credit: "กันเครดิตแล้ว",
    approved: "อนุมัติแล้ว",
    packed: "แพ็กแล้ว",
    shipped: "จัดส่งแล้ว",
    partially_received: "รับบางส่วน",
    received: "รับแล้ว",
    cancelled: "ยกเลิก",
  };
  return labels[status] ?? status;
}

export default function RestaurantStoreOrdersPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [receiveOrder, setReceiveOrder] = useState<CentralOrder | null>(null);
  const [receivedByItem, setReceivedByItem] = useState<Record<string, number>>({});
  const [receiveNote, setReceiveNote] = useState("");
  const ordersQuery = useQuery({
    queryKey: ["restaurant-store-central-orders", brandSlug ?? "legacy"],
    queryFn: async () => (await wapApi.branchCentralOrders(brandSlug)).data.data,
  });
  const storeBase = brandSlug ? `/store/${brandSlug}` : "/restaurant";

  const receiveMutation = useMutation({
    mutationFn: async ({ order, finalize }: { order: CentralOrder; finalize: boolean }) => (
      await wapApi.receiveBranchCentralOrder(order.id, brandSlug, {
        items: (order.items ?? []).filter((item) => item.id).map((item) => ({
          item_id: item.id as string,
          qty_received: Number(receivedByItem[item.id as string] ?? item.received_qty ?? 0),
        })),
        finalize,
        note: receiveNote.trim() || null,
      })
    ).data.data,
    onSuccess: async (order) => {
      toast({
        title: order.status === "received"
          ? `รับสินค้าเสร็จแล้ว: ${order.order_number}`
          : `บันทึกรับบางส่วน: ${order.order_number}`,
        description: order.transfer_order_number ? `Transfer: ${order.transfer_order_number}` : undefined,
      });
      setReceiveOrder(null);
      setReceiveNote("");
      await queryClient.invalidateQueries({ queryKey: ["restaurant-store-central-orders", brandSlug ?? "legacy"] });
    },
    onError: (error) => {
      toast({
        title: "รับสินค้าไม่สำเร็จ",
        description: error instanceof Error ? error.message : "",
        variant: "destructive",
      });
    },
  });

  function openReceive(order: CentralOrder): void {
    setReceiveOrder(order);
    setReceivedByItem(Object.fromEntries(
      (order.items ?? []).filter((item) => item.id).map((item) => [
        item.id as string,
        Number(item.shipped_qty ?? item.received_qty ?? 0),
      ])
    ));
    setReceiveNote("");
  }

  const receiveHasShortage = Boolean(receiveOrder?.items?.some((item) => (
    Number(receivedByItem[item.id ?? ""] ?? item.received_qty ?? 0) < Number(item.shipped_qty ?? 0)
  )));
  const receiveHasIncrease = Boolean(receiveOrder?.items?.some((item) => (
    Number(receivedByItem[item.id ?? ""] ?? 0) > Number(item.received_qty ?? 0)
  )));
  const receiveQuantitiesValid = Boolean(receiveOrder?.items?.every((item) => {
    const target = Number(receivedByItem[item.id ?? ""] ?? item.received_qty ?? 0);
    return target >= Number(item.received_qty ?? 0) && target <= Number(item.shipped_qty ?? 0);
  }));

  return (
    <div className="mx-auto flex min-h-full max-w-4xl flex-col gap-4">
      <header className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 p-4">
          <div className="flex min-w-0 items-center gap-3">
            <Button asChild variant="outline" size="icon" className="h-10 w-10 shrink-0">
              <Link to={`${storeBase}/orders`} aria-label="กลับหน้ารับออเดอร์">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-black text-slate-950">รายการสั่งสินค้า</h1>
              <p className="truncate text-sm text-slate-500">ติดตามสถานะและรับของจากครัวกลาง</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={`${storeBase}/credits`}>
                <CreditCard className="mr-2 h-4 w-4" />
                เติมเครดิต
              </Link>
            </Button>
            <span className="hidden rounded-full bg-slate-100 px-3 py-1.5 text-sm font-semibold text-slate-700 sm:inline-flex">
              {ordersQuery.data?.length ?? 0} ใบสั่ง
            </span>
          </div>
        </div>
      </header>

      {ordersQuery.isLoading ? (
        <div className="flex h-72 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          โหลดรายการสั่งสินค้า
        </div>
      ) : ordersQuery.isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-center font-semibold text-rose-700">
          โหลดรายการสั่งสินค้าไม่สำเร็จ
        </div>
      ) : (
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center gap-2 border-b border-slate-200 p-4">
            <ClipboardList className="h-5 w-5 text-slate-700" />
            <h2 className="font-bold text-slate-950">ใบสั่งของสาขา</h2>
          </div>
          <div className="divide-y divide-slate-100">
            {(ordersQuery.data ?? []).length > 0 ? ordersQuery.data?.map((order) => (
              <div key={order.id} className="space-y-3 px-4 py-4">
                <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="min-w-0">
                    <p className="font-bold text-slate-950">{order.order_number}</p>
                    <p className="text-sm text-slate-500">
                      ส่งคำขอ {formatDateTime(order.submitted_at)}
                      {order.shipped_at ? ` · จัดส่ง ${formatDateTime(order.shipped_at)}` : ""}
                      {order.received_at ? ` · รับแล้ว ${formatDateTime(order.received_at)}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 sm:justify-end">
                    <span className="rounded-full bg-orange-100 px-3 py-1 text-sm font-bold text-orange-700">
                      {statusLabel(order.status)}
                    </span>
                    {["shipped", "partially_received"].includes(order.status) ? (
                      <Button
                        size="sm"
                        className="bg-emerald-600 hover:bg-emerald-700"
                        disabled={receiveMutation.isPending}
                        onClick={() => openReceive(order)}
                      >
                        {receiveMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
                        {order.status === "partially_received" ? "รับเพิ่ม" : "รับของ"}
                      </Button>
                    ) : null}
                  </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg border border-slate-200 px-3 py-2">
                    <div className="flex items-center gap-2 text-xs font-bold uppercase text-slate-500">
                      <Truck className="h-4 w-4" />
                      Transfer
                    </div>
                    <p className="mt-1 font-bold text-slate-950">
                      {order.transfer_order_number ?? (order.transfer_order_id ? "สร้างแล้ว" : "รอสร้างหลังจัดส่ง")}
                    </p>
                    <p className="text-sm text-slate-500">{order.transfer_order_status ?? "ยังไม่มีสถานะใบโอน"}</p>
                    {order.transfer_has_discrepancy ? (
                      <p className="mt-1 text-xs font-semibold text-rose-600">ปิดรับพร้อมส่วนต่าง</p>
                    ) : null}
                  </div>
                  <div className="rounded-lg border border-slate-200 px-3 py-2">
                    <div className="flex items-center gap-2 text-xs font-bold uppercase text-slate-500">
                      <CreditCard className="h-4 w-4" />
                      เครดิต
                    </div>
                    <p className="mt-1 font-bold text-slate-950">
                      ตัดจริง {formatMoney(order.credit_captured_amount)}
                    </p>
                    <p className="text-sm text-slate-500">
                      กันไว้ {formatMoney(order.credit_reserved_amount)} · คืน {formatMoney(order.credit_released_amount)}
                    </p>
                  </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {(order.items ?? []).map((item) => (
                    <div key={item.id ?? item.sku} className="rounded-lg bg-slate-50 px-3 py-2">
                      <p className="font-semibold text-slate-950">{item.product_name}</p>
                      <p className="text-sm text-slate-500">
                        สั่ง {formatQty(item.requested_qty)} · ส่ง {formatQty(item.shipped_qty ?? 0)} · รับ {formatQty(item.received_qty ?? 0)}
                        {(item.in_transit_qty ?? 0) > 0 ? ` · ระหว่างทาง ${formatQty(item.in_transit_qty ?? 0)}` : ""}
                        {(item.discrepancy_qty ?? 0) > 0 ? ` · ขาด ${formatQty(item.discrepancy_qty ?? 0)}` : ""} {item.unit}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )) : (
              <div className="p-8 text-center text-slate-500">
                <PackageOpen className="mx-auto mb-2 h-8 w-8 text-slate-400" />
                ยังไม่มีใบสั่งสินค้า
              </div>
            )}
          </div>
        </section>
      )}

      <Dialog open={Boolean(receiveOrder)} onOpenChange={(open) => !open && setReceiveOrder(null)}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-auto">
          <DialogHeader>
            <DialogTitle>ตรวจรับสินค้าจากส่วนกลาง</DialogTitle>
            <DialogDescription>
              {receiveOrder?.order_number ?? ""} · กรอกยอดรับสะสมจริง ร้านจะเพิ่ม stock ตามยอดที่เพิ่มครั้งนี้เท่านั้น
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {(receiveOrder?.items ?? []).map((item) => (
              <div key={item.id ?? item.sku} className="grid gap-3 rounded-lg border border-slate-200 p-3 sm:grid-cols-[1fr_150px] sm:items-center">
                <div>
                  <p className="font-bold text-slate-950">{item.product_name}</p>
                  <p className="text-sm text-slate-500">
                    ส่ง {formatQty(item.shipped_qty ?? 0)} · เคยรับ {formatQty(item.received_qty ?? 0)} {item.unit}
                  </p>
                </div>
                <div>
                  <p className="mb-1 text-xs font-semibold text-slate-500">ยอดรับสะสมจริง</p>
                  <Input
                    type="number"
                    min={item.received_qty ?? 0}
                    max={item.shipped_qty ?? 0}
                    step="0.01"
                    value={receivedByItem[item.id ?? ""] ?? 0}
                    onChange={(event) => {
                      if (!item.id) return;
                      setReceivedByItem((current) => ({
                        ...current,
                        [item.id as string]: Number(event.target.value),
                      }));
                    }}
                  />
                </div>
              </div>
            ))}
            <div>
              <p className="mb-1 text-sm font-semibold text-slate-600">
                หมายเหตุ {receiveHasShortage ? "(จำเป็นเมื่อปิดรับโดยมีส่วนต่าง)" : ""}
              </p>
              <textarea
                className="min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                value={receiveNote}
                onChange={(event) => setReceiveNote(event.target.value)}
                placeholder="เช่น สินค้าขาด 1 ถุง หรือกล่องเสียหาย"
              />
            </div>
            {receiveHasShortage ? (
              <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                ยอดรับน้อยกว่ายอดส่ง: เลือก “รับบางส่วน” หากยังมีของตามมา หรือ “ปิดรับ” เพื่อบันทึกเป็นส่วนต่าง
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReceiveOrder(null)}>ยกเลิก</Button>
            {receiveHasShortage ? (
              <Button
                variant="outline"
                disabled={!receiveQuantitiesValid || !receiveHasIncrease || receiveMutation.isPending || !receiveOrder}
                onClick={() => receiveOrder && receiveMutation.mutate({ order: receiveOrder, finalize: false })}
              >
                บันทึกรับบางส่วน
              </Button>
            ) : null}
            <Button
              className={receiveHasShortage ? "bg-amber-600 hover:bg-amber-700" : "bg-emerald-600 hover:bg-emerald-700"}
              disabled={
                !receiveQuantitiesValid
                || (!receiveHasIncrease && !receiveHasShortage)
                || (receiveHasShortage && !receiveNote.trim())
                || receiveMutation.isPending
                || !receiveOrder
              }
              onClick={() => receiveOrder && receiveMutation.mutate({ order: receiveOrder, finalize: true })}
            >
              {receiveMutation.isPending
                ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                : <CheckCircle2 className="mr-2 h-4 w-4" />}
              {receiveHasShortage ? "ปิดรับและแจ้งส่วนต่าง" : "ยืนยันรับครบ"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
