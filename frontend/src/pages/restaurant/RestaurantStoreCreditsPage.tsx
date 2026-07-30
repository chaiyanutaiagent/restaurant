import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Clock3, CreditCard, Loader2, Upload, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { wapApi, type CreditTopupRequest } from "@/lib/wapApi";

const PRESET_AMOUNTS = [500, 1000, 3000, 5000, 10000];
const MIN_AMOUNT = 500;

function money(value: number): string {
  return `฿${value.toLocaleString("th-TH", { maximumFractionDigits: 2 })}`;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

function statusMeta(status: string): { label: string; className: string; icon: JSX.Element } {
  if (status === "approved") {
    return { label: "อนุมัติแล้ว", className: "bg-emerald-100 text-emerald-700", icon: <CheckCircle2 className="h-4 w-4" /> };
  }
  if (status === "rejected") {
    return { label: "ไม่อนุมัติ", className: "bg-rose-100 text-rose-700", icon: <XCircle className="h-4 w-4" /> };
  }
  return { label: "รอตรวจสลิป", className: "bg-amber-100 text-amber-700", icon: <Clock3 className="h-4 w-4" /> };
}

export default function RestaurantStoreCreditsPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [amountMode, setAmountMode] = useState<"preset" | "custom">("preset");
  const [presetAmount, setPresetAmount] = useState(PRESET_AMOUNTS[0]);
  const [customAmount, setCustomAmount] = useState(String(MIN_AMOUNT));
  const [note, setNote] = useState("");
  const [slipFile, setSlipFile] = useState<File | null>(null);
  const storeBase = brandSlug ? `/store/${brandSlug}` : "/restaurant";

  const selectedAmount = amountMode === "preset" ? presetAmount : Number(customAmount || 0);
  const amountError = amountMode === "custom" && selectedAmount < MIN_AMOUNT ? "ยอดเติมเครดิตขั้นต่ำ 500 บาท" : null;

  const requestsQuery = useQuery({
    queryKey: ["store-credit-topup-requests", brandSlug],
    queryFn: async () => {
      if (!brandSlug) return [];
      return (await wapApi.storeCreditTopupRequests(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
  });
  const paymentConfigQuery = useQuery({
    queryKey: ["store-credit-payment-config", brandSlug],
    queryFn: async () => {
      if (!brandSlug) return { credit_topup_qr_url: null };
      return (await wapApi.storeCreditPaymentConfig(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
  });

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      if (selectedAmount < MIN_AMOUNT) throw new Error("ยอดเติมเครดิตขั้นต่ำ 500 บาท");
      if (!slipFile) throw new Error("กรุณาแนบสลิปโอนเงิน");
      const formData = new FormData();
      formData.append("amount", String(selectedAmount));
      formData.append("note", note.trim());
      formData.append("slip", slipFile);
      return (await wapApi.createStoreCreditTopupRequest(brandSlug, formData)).data.data;
    },
    onSuccess: async () => {
      toast({ title: "ส่งคำขอเติมเครดิตแล้ว", description: "ส่วนกลางจะตรวจสลิปและอนุมัติยอดเครดิต" });
      setAmountMode("preset");
      setPresetAmount(PRESET_AMOUNTS[0]);
      setCustomAmount(String(MIN_AMOUNT));
      setNote("");
      setSlipFile(null);
      await queryClient.invalidateQueries({ queryKey: ["store-credit-topup-requests", brandSlug] });
    },
    onError: (error) => {
      toast({
        title: "ส่งคำขอไม่สำเร็จ",
        description: error instanceof Error ? error.message : "",
        variant: "destructive",
      });
    },
  });

  const latestPending = useMemo(
    () => (requestsQuery.data ?? []).filter((request) => request.status === "pending").length,
    [requestsQuery.data]
  );

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
              <h1 className="truncate text-xl font-black text-slate-950">แจ้งเติมเครดิต</h1>
              <p className="truncate text-sm text-slate-500">โอนผ่าน QR บริษัทแล้วแนบสลิปเพื่อให้ส่วนกลางตรวจสอบ</p>
            </div>
          </div>
          <span className="hidden rounded-full bg-amber-100 px-3 py-1.5 text-sm font-semibold text-amber-700 sm:inline-flex">
            รอตรวจ {latestPending} รายการ
          </span>
        </div>
      </header>

      <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 p-4">
            <h2 className="font-bold text-slate-950">เลือกยอดเติมเครดิต</h2>
          </div>
          <div className="space-y-5 p-4">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-sm font-bold text-slate-700">QR โอนเงินบริษัท</p>
              {paymentConfigQuery.isLoading ? (
                <div className="mt-3 flex h-48 items-center justify-center text-slate-500">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  โหลด QR
                </div>
              ) : paymentConfigQuery.data?.credit_topup_qr_url ? (
                <div className="mt-3 flex justify-center">
                  <img
                    src={paymentConfigQuery.data.credit_topup_qr_url}
                    alt="QR โอนเงินบริษัท"
                    className="max-h-72 rounded-md border border-slate-200 bg-white object-contain"
                  />
                </div>
              ) : (
                <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-700">
                  ยังไม่ได้ตั้งค่า QR บริษัทสำหรับแบรนด์นี้
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {PRESET_AMOUNTS.map((amount) => (
                <Button
                  key={amount}
                  type="button"
                  variant={amountMode === "preset" && presetAmount === amount ? "default" : "outline"}
                  className={amountMode === "preset" && presetAmount === amount ? "bg-emerald-600 hover:bg-emerald-700" : ""}
                  onClick={() => {
                    setAmountMode("preset");
                    setPresetAmount(amount);
                  }}
                >
                  {money(amount)}
                </Button>
              ))}
            </div>

            <div className="rounded-lg border border-slate-200 p-3">
              <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <input
                  type="radio"
                  checked={amountMode === "custom"}
                  onChange={() => setAmountMode("custom")}
                />
                กำหนดยอดเอง
              </label>
              <Input
                className="mt-3"
                type="number"
                min={MIN_AMOUNT}
                step="1"
                value={customAmount}
                onFocus={() => setAmountMode("custom")}
                onChange={(event) => setCustomAmount(event.target.value)}
              />
              {amountError ? <p className="mt-2 text-sm font-semibold text-rose-600">{amountError}</p> : null}
            </div>

            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-700">แนบสลิปโอนเงิน</p>
              <Input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={(event) => setSlipFile(event.target.files?.[0] ?? null)}
              />
              {slipFile ? <p className="text-sm text-slate-500">{slipFile.name}</p> : null}
            </div>

            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-700">หมายเหตุ</p>
              <Input value={note} onChange={(event) => setNote(event.target.value)} placeholder="เช่น โอนจากบัญชี..." />
            </div>

            <Button
              className="w-full bg-emerald-600 hover:bg-emerald-700"
              disabled={submitMutation.isPending || selectedAmount < MIN_AMOUNT || !slipFile}
              onClick={() => submitMutation.mutate()}
            >
              {submitMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
              ส่งคำขอเติมเครดิต {money(selectedAmount || 0)}
            </Button>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center gap-2 border-b border-slate-200 p-4">
            <CreditCard className="h-5 w-5 text-emerald-700" />
            <h2 className="font-bold text-slate-950">ประวัติแจ้งเติมเครดิต</h2>
          </div>
          <div className="divide-y divide-slate-100">
            {requestsQuery.isLoading ? (
              <div className="flex h-40 items-center justify-center text-slate-500">
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                โหลดคำขอ
              </div>
            ) : (requestsQuery.data ?? []).length > 0 ? (
              requestsQuery.data?.map((request: CreditTopupRequest) => {
                const status = statusMeta(request.status);
                return (
                  <div key={request.id} className="space-y-2 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-black text-slate-950">{money(request.amount)}</p>
                        <p className="text-sm text-slate-500">{formatDateTime(request.created_at)}</p>
                      </div>
                      <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm font-bold ${status.className}`}>
                        {status.icon}
                        {status.label}
                      </span>
                    </div>
                    {request.review_note ? <p className="text-sm text-slate-500">หมายเหตุ: {request.review_note}</p> : null}
                    <a className="text-sm font-semibold text-emerald-700 hover:underline" href={request.slip_url} target="_blank" rel="noreferrer">
                      เปิดดูสลิป
                    </a>
                  </div>
                );
              })
            ) : (
              <div className="p-8 text-center text-slate-500">ยังไม่มีคำขอเติมเครดิต</div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
