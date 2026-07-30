import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, ChefHat, CreditCard, ExternalLink, Factory, History, Loader2, RotateCcw, XCircle } from "lucide-react";
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
import { wapApi, type CreditAccount } from "@/lib/wapApi";

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

export default function RestaurantCentralCreditsPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [topupAccount, setTopupAccount] = useState<CreditAccount | null>(null);
  const [refundAccount, setRefundAccount] = useState<CreditAccount | null>(null);
  const [ledgerAccount, setLedgerAccount] = useState<CreditAccount | null>(null);
  const [topupAmount, setTopupAmount] = useState("");
  const [refundAmount, setRefundAmount] = useState("");
  const [refundNote, setRefundNote] = useState("");
  const [paymentQrFile, setPaymentQrFile] = useState<File | null>(null);

  const centralBase = brandSlug ? `/central/${brandSlug}` : "/restaurant";

  const creditQuery = useQuery({
    queryKey: ["restaurant-credit-accounts", brandSlug],
    queryFn: async () => {
      if (!brandSlug) return [];
      return (await wapApi.creditAccounts(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
  });
  const locationsQuery = useQuery({
    queryKey: ["restaurant-config-locations", brandSlug],
    queryFn: async () => (await wapApi.stockLocations()).data.data,
    enabled: Boolean(brandSlug),
  });
  const ledgerQuery = useQuery({
    queryKey: ["restaurant-credit-ledger", brandSlug, ledgerAccount?.id],
    queryFn: async () => {
      if (!brandSlug || !ledgerAccount) return [];
      return (await wapApi.creditLedger(brandSlug, ledgerAccount.id)).data.data;
    },
    enabled: Boolean(brandSlug && ledgerAccount),
  });
  const topupRequestsQuery = useQuery({
    queryKey: ["central-credit-topup-requests", brandSlug, "pending"],
    queryFn: async () => {
      if (!brandSlug) return [];
      return (await wapApi.centralCreditTopupRequests(brandSlug, "pending")).data.data;
    },
    enabled: Boolean(brandSlug),
  });
  const paymentConfigQuery = useQuery({
    queryKey: ["central-credit-payment-config", brandSlug],
    queryFn: async () => {
      if (!brandSlug) return { credit_topup_qr_url: null };
      return (await wapApi.centralCreditPaymentConfig(brandSlug)).data.data;
    },
    enabled: Boolean(brandSlug),
  });

  async function refreshCredits(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["restaurant-credit-accounts", brandSlug] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-credit-ledger", brandSlug, ledgerAccount?.id] }),
      queryClient.invalidateQueries({ queryKey: ["central-credit-topup-requests", brandSlug, "pending"] }),
      queryClient.invalidateQueries({ queryKey: ["central-credit-payment-config", brandSlug] }),
    ]);
  }

  const topupMutation = useMutation({
    mutationFn: async () => {
      if (!brandSlug || !topupAccount) throw new Error("ยังไม่ได้เลือกบัญชีเครดิต");
      return (await wapApi.topupCredit(brandSlug, {
        branch_id: topupAccount.branch_id,
        amount: Number(topupAmount),
        note: "เติมเครดิตจากหน้าครัวกลาง",
      })).data.data;
    },
    onSuccess: async (account) => {
      toast({ title: `เติมเครดิตแล้ว: ${account.branch_name ?? ""}` });
      setTopupAccount(null);
      setTopupAmount("");
      await refreshCredits();
    },
    onError: (error) => toast({ title: "เติมเครดิตไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });
  const branchTypeMutation = useMutation({
    mutationFn: async (account: CreditAccount) => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      const nextType = account.branch_type === "franchise" ? "company_owned" : "franchise";
      return (await wapApi.updateBrandBranchType(brandSlug, account.branch_id, nextType)).data.data;
    },
    onSuccess: async (account) => {
      toast({ title: `อัปเดตประเภทสาขาแล้ว: ${account.branch_name ?? ""}` });
      await refreshCredits();
    },
    onError: (error) => toast({ title: "อัปเดตประเภทสาขาไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });
  const refundMutation = useMutation({
    mutationFn: async () => {
      if (!brandSlug || !refundAccount) throw new Error("ยังไม่ได้เลือกบัญชีเครดิต");
      return (await wapApi.refundCredit(brandSlug, {
        branch_id: refundAccount.branch_id,
        amount: Number(refundAmount),
        note: refundNote.trim() || "คืนเครดิตจากหน้าครัวกลาง",
      })).data.data;
    },
    onSuccess: async (account) => {
      toast({ title: `คืนเครดิตแล้ว: ${account.branch_name ?? ""}` });
      setRefundAccount(null);
      setRefundAmount("");
      setRefundNote("");
      await refreshCredits();
    },
    onError: (error) => toast({ title: "คืนเครดิตไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });
  const approveTopupRequestMutation = useMutation({
    mutationFn: async (requestId: string) => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return (await wapApi.approveCreditTopupRequest(brandSlug, requestId)).data.data;
    },
    onSuccess: async (request) => {
      toast({ title: `อนุมัติเติมเครดิตแล้ว: ฿${request.amount.toLocaleString("th-TH")}` });
      await refreshCredits();
    },
    onError: (error) => toast({ title: "อนุมัติไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });
  const rejectTopupRequestMutation = useMutation({
    mutationFn: async (requestId: string) => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return (await wapApi.rejectCreditTopupRequest(brandSlug, requestId, "สลิปไม่ผ่านการตรวจสอบ")).data.data;
    },
    onSuccess: async () => {
      toast({ title: "ปฏิเสธคำขอเติมเครดิตแล้ว" });
      await refreshCredits();
    },
    onError: (error) => toast({ title: "ปฏิเสธไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });
  const uploadPaymentQrMutation = useMutation({
    mutationFn: async () => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      if (!paymentQrFile) throw new Error("กรุณาเลือกไฟล์ QR");
      const formData = new FormData();
      formData.append("qr", paymentQrFile);
      return (await wapApi.uploadCentralCreditPaymentQr(brandSlug, formData)).data.data;
    },
    onSuccess: async () => {
      toast({ title: "บันทึก QR บริษัทแล้ว" });
      setPaymentQrFile(null);
      await refreshCredits();
    },
    onError: (error) => toast({ title: "บันทึก QR ไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });
  const storeLocationMutation = useMutation({
    mutationFn: async ({ account, locationId }: { account: CreditAccount; locationId: string }) => {
      if (!brandSlug) throw new Error("ไม่พบแบรนด์");
      return (await wapApi.updateBranchTransferConfig(brandSlug, account.branch_id, { store_location_id: locationId || null })).data.data;
    },
    onSuccess: async (account) => {
      toast({ title: `บันทึกคลังสาขาแล้ว: ${account.branch_name ?? ""}` });
      await refreshCredits();
    },
    onError: (error) => toast({ title: "บันทึกคลังสาขาไม่สำเร็จ", description: error instanceof Error ? error.message : "", variant: "destructive" }),
  });

  const accounts = creditQuery.data ?? [];

  return (
    <div className="mx-auto flex min-h-full max-w-5xl flex-col gap-4">
      <header className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 p-4">
          <div className="flex min-w-0 items-center gap-3">
            <Button asChild variant="outline" size="icon" className="h-10 w-10 shrink-0">
              <Link to={`${centralBase}/orders`} aria-label="กลับหน้าใบสั่ง">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-black text-slate-950">เครดิตแฟรนไชส์</h1>
              <p className="truncate text-sm text-slate-500">จัดการเครดิต ประเภทสาขา คลังสาขา และประวัติรายการ</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/production`}>
                <Factory className="mr-2 h-4 w-4" />
                ผลิต
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/recipes`}>
                <ChefHat className="mr-2 h-4 w-4" />
                สูตร
              </Link>
            </Button>
          </div>
        </div>
      </header>

      <section className="rounded-lg border border-slate-200 bg-white">
        <div className="grid gap-4 p-4 md:grid-cols-[220px_1fr] md:items-center">
          <div className="flex h-56 items-center justify-center rounded-lg border border-slate-200 bg-slate-50">
            {paymentConfigQuery.isLoading ? (
              <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            ) : paymentConfigQuery.data?.credit_topup_qr_url ? (
              <img
                src={paymentConfigQuery.data.credit_topup_qr_url}
                alt="QR โอนเงินบริษัท"
                className="max-h-52 max-w-full rounded-md object-contain"
              />
            ) : (
              <span className="text-sm font-semibold text-slate-400">ยังไม่มี QR</span>
            )}
          </div>
          <div className="space-y-3">
            <div>
              <h2 className="font-bold text-slate-950">QR บริษัทสำหรับเติมเครดิต</h2>
              <p className="text-sm text-slate-500">รูปนี้จะแสดงในหน้าแจ้งเติมเครดิตของสาขาแบรนด์นี้</p>
            </div>
            <Input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(event) => setPaymentQrFile(event.target.files?.[0] ?? null)}
            />
            {paymentQrFile ? <p className="text-sm text-slate-500">{paymentQrFile.name}</p> : null}
            <Button
              className="bg-slate-950 hover:bg-slate-800"
              disabled={uploadPaymentQrMutation.isPending || !paymentQrFile}
              onClick={() => uploadPaymentQrMutation.mutate()}
            >
              {uploadPaymentQrMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CreditCard className="mr-2 h-4 w-4" />}
              บันทึก QR บริษัท
            </Button>
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-amber-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-amber-100 p-4">
          <div>
            <h2 className="font-bold text-slate-950">คำขอเติมเครดิตรอตรวจ</h2>
            <p className="text-sm text-slate-500">ตรวจสลิปโอนเงินก่อนอนุมัติยอดเข้าเครดิตสาขา</p>
          </div>
          <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-bold text-amber-700">
            {(topupRequestsQuery.data ?? []).length} รายการ
          </span>
        </div>
        <div className="divide-y divide-slate-100">
          {topupRequestsQuery.isLoading ? (
            <div className="flex h-28 items-center justify-center text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              โหลดคำขอเติมเครดิต
            </div>
          ) : (topupRequestsQuery.data ?? []).length > 0 ? topupRequestsQuery.data?.map((request) => (
            <div key={request.id} className="grid gap-3 px-4 py-3 lg:grid-cols-[1fr_auto] lg:items-center">
              <div className="min-w-0">
                <p className="font-bold text-slate-950">{request.branch_name ?? "ไม่ระบุสาขา"} · ฿{request.amount.toLocaleString("th-TH")}</p>
                <p className="text-sm text-slate-500">
                  ส่งคำขอ {formatDateTime(request.created_at)}
                  {request.note ? ` · ${request.note}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                <Button asChild size="sm" variant="outline">
                  <a href={request.slip_url} target="_blank" rel="noreferrer">
                    <ExternalLink className="mr-1 h-4 w-4" />
                    เปิดสลิป
                  </a>
                </Button>
                <Button
                  size="sm"
                  className="bg-emerald-600 hover:bg-emerald-700"
                  disabled={approveTopupRequestMutation.isPending || rejectTopupRequestMutation.isPending}
                  onClick={() => approveTopupRequestMutation.mutate(request.id)}
                >
                  <CheckCircle2 className="mr-1 h-4 w-4" />
                  อนุมัติ
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={approveTopupRequestMutation.isPending || rejectTopupRequestMutation.isPending}
                  onClick={() => rejectTopupRequestMutation.mutate(request.id)}
                >
                  <XCircle className="mr-1 h-4 w-4" />
                  ปฏิเสธ
                </Button>
              </div>
            </div>
          )) : (
            <div className="p-6 text-center text-slate-500">ไม่มีคำขอเติมเครดิตที่รอตรวจ</div>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center gap-2 border-b border-slate-200 p-4">
          <CreditCard className="h-5 w-5 text-emerald-700" />
          <h2 className="font-bold text-slate-950">บัญชีเครดิตรายสาขา</h2>
        </div>
        <div className="divide-y divide-slate-100">
          {creditQuery.isLoading ? (
            <div className="flex h-40 items-center justify-center text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              โหลดเครดิต
            </div>
          ) : accounts.length > 0 ? accounts.map((account) => (
            <div key={account.id} className="grid gap-3 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <div className="min-w-0">
                <p className="font-bold text-slate-950">{account.branch_name ?? "ไม่ระบุสาขา"}</p>
                <p className="text-sm text-slate-500">
                  {account.branch_type === "franchise" ? "แฟรนไชส์" : "สาขาบริษัท"} · กันไว้ ฿{account.reserved_amount.toLocaleString("th-TH")}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                <select
                  className="h-9 max-w-48 rounded-md border border-gray-300 px-2 text-sm"
                  value={account.store_location_id ?? ""}
                  onChange={(event) => storeLocationMutation.mutate({ account, locationId: event.target.value })}
                >
                  <option value="">เลือกคลังสาขา</option>
                  {(locationsQuery.data ?? [])
                    .filter((location) => location.branch_id === account.branch_id)
                    .map((location) => (
                      <option key={location.id} value={location.id}>{location.name}</option>
                    ))}
                </select>
                <div className="min-w-28 text-right">
                  <p className="text-sm font-semibold text-slate-500">ใช้ได้</p>
                  <p className="text-lg font-black text-emerald-700">฿{account.available_credit.toLocaleString("th-TH")}</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => setTopupAccount(account)}>
                  เติมเครดิต
                </Button>
                <Button size="sm" variant="outline" onClick={() => setRefundAccount(account)}>
                  <RotateCcw className="mr-1 h-4 w-4" />
                  คืนเครดิต
                </Button>
                <Button size="sm" variant="outline" onClick={() => setLedgerAccount(account)}>
                  <History className="mr-1 h-4 w-4" />
                  ประวัติ
                </Button>
                <Button size="sm" variant="outline" onClick={() => branchTypeMutation.mutate(account)}>
                  {account.branch_type === "franchise" ? "ตั้งเป็นสาขาบริษัท" : "ตั้งเป็นแฟรนไชส์"}
                </Button>
              </div>
            </div>
          )) : (
            <div className="p-8 text-center text-slate-500">ยังไม่มีบัญชีเครดิต</div>
          )}
        </div>
      </section>

      <Dialog open={Boolean(topupAccount)} onOpenChange={(open) => !open && setTopupAccount(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>เติมเครดิต</DialogTitle>
            <DialogDescription>{topupAccount?.branch_name ?? "สาขา"}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-600">จำนวนเงิน</p>
            <Input
              type="number"
              min="0"
              step="1"
              value={topupAmount}
              onChange={(event) => setTopupAmount(event.target.value)}
              placeholder="0.00"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTopupAccount(null)}>ยกเลิก</Button>
            <Button
              className="bg-emerald-600 hover:bg-emerald-700"
              disabled={topupMutation.isPending || Number(topupAmount) <= 0}
              onClick={() => topupMutation.mutate()}
            >
              {topupMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CreditCard className="mr-2 h-4 w-4" />}
              เติมเครดิต
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(refundAccount)} onOpenChange={(open) => !open && setRefundAccount(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>คืนเครดิต</DialogTitle>
            <DialogDescription>{refundAccount?.branch_name ?? "สาขา"}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-600">จำนวนเงิน</p>
              <Input
                type="number"
                min="0"
                step="1"
                value={refundAmount}
                onChange={(event) => setRefundAmount(event.target.value)}
                placeholder="0.00"
              />
            </div>
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-600">หมายเหตุ</p>
              <Input
                value={refundNote}
                onChange={(event) => setRefundNote(event.target.value)}
                placeholder="เช่น คืนเครดิตจากการส่งคืนสินค้า"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRefundAccount(null)}>ยกเลิก</Button>
            <Button
              className="bg-cyan-700 hover:bg-cyan-800"
              disabled={refundMutation.isPending || Number(refundAmount) <= 0}
              onClick={() => refundMutation.mutate()}
            >
              {refundMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4" />}
              คืนเครดิต
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(ledgerAccount)} onOpenChange={(open) => !open && setLedgerAccount(null)}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-auto">
          <DialogHeader>
            <DialogTitle>ประวัติเครดิต</DialogTitle>
            <DialogDescription>{ledgerAccount?.branch_name ?? "สาขา"}</DialogDescription>
          </DialogHeader>
          {ledgerQuery.isLoading ? (
            <div className="flex h-40 items-center justify-center text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              โหลดประวัติเครดิต
            </div>
          ) : (ledgerQuery.data ?? []).length > 0 ? (
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {ledgerQuery.data?.map((entry) => (
                <div key={entry.id} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div>
                    <p className="font-bold text-slate-950">{entry.entry_type}</p>
                    <p className="text-sm text-slate-500">
                      {formatDateTime(entry.created_at)}
                      {entry.note ? ` · ${entry.note}` : ""}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-black text-slate-950">฿{entry.amount.toLocaleString("th-TH")}</p>
                    <p className="text-xs text-slate-500">
                      คงเหลือ ฿{entry.balance_after.toLocaleString("th-TH")} · กันไว้ ฿{entry.reserved_after.toLocaleString("th-TH")}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-500">
              ยังไม่มีประวัติเครดิต
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setLedgerAccount(null)}>ปิด</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
