import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2, ChefHat, Loader2, Printer, ReceiptText } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import { fbApi } from "@/lib/fbApi";
import { posApi } from "@/lib/posApi";
import { useAuthStore } from "@/stores/auth.store";
import { formatThaiCurrency } from "@/lib/cartUtils";
import type { CashierShift } from "@/types/pos";
import type { StockLocation } from "@/types/stock";
import ManagerApprovalDialog from "@/components/approval/ManagerApprovalDialog";
import { errorMessage } from "@/lib/approvalApi";

type SessionItem = { id: string; product_name: string; qty: number; unit_price: number; special_request: string | null; status: string };
type SessionOrder = { id: string; status: string; source?: string; order_number?: string; items: SessionItem[] };
type SessionData = { id: string; status: string; queue_number: number | null; table_name?: string; customer_name: string | null; customer_phone: string | null; orders: SessionOrder[] };
type CheckoutResult = {
  sale_order_id: string;
  order_number: string;
  total_amount: number;
  paid_amount: number;
  change_amount: number;
  session_id: string;
  table_name: string | null;
  queue_number: number | null;
  source_type: "dine_in" | "quick_service" | string;
  customer_name: string | null;
  customer_phone: string | null;
  payment_method: PaymentMethod;
  note: string | null;
};

type PaymentMethod = "cash" | "promptpay" | "credit_card" | "bank_transfer" | "other";
const PAYMENT_LABELS: Record<PaymentMethod, string> = { cash: "เงินสด", promptpay: "PromptPay", credit_card: "บัตรเครดิต", bank_transfer: "โอนเงิน", other: "อื่นๆ" };
const SOURCE_LABELS: Record<string, string> = { dine_in: "โต๊ะ", quick_service: "รับเอง / กลับบ้าน" };

export default function SessionCheckoutPage(): JSX.Element {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const branchId = useAuthStore((s) => s.branchId);
  const hasPermission = useAuthStore((s) => s.hasPermission);

  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("cash");
  const [paidAmount, setPaidAmount] = useState(0);
  const [creditRef, setCreditRef] = useState("");
  const [discount, setDiscount] = useState(0);
  const [checkoutResult, setCheckoutResult] = useState<CheckoutResult | null>(null);
  const [paymentQrImageLoaded, setPaymentQrImageLoaded] = useState(false);
  const [receiptLogoLoaded, setReceiptLogoLoaded] = useState(true);
  const [managerApprovalOpen, setManagerApprovalOpen] = useState(false);
  const receiptRef = useRef<HTMLDivElement>(null);
  const autoPrintStartedRef = useRef(false);

  // ดึงข้อมูล session
  const sessionQuery = useQuery({
    queryKey: ["dining-session", sessionId],
    queryFn: async () => (await authApi.get(`/restaurant/sessions/${sessionId}/detail`)).data.data as SessionData,
    enabled: Boolean(sessionId),
  });

  // ดึง current shift
  const shiftQuery = useQuery({
    queryKey: ["pos", "current-shift", branchId],
    queryFn: async () => (await posApi.getCurrentShift()).data.data as CashierShift | null,
    enabled: Boolean(branchId),
  });

  // ดึง locations
  const locationsQuery = useQuery({
    queryKey: ["pos", "locations", branchId],
    queryFn: async () => (await posApi.listLocations(branchId ?? undefined)).data.data as StockLocation[],
    enabled: Boolean(branchId),
  });

  const branchSettingsQuery = useQuery({
    queryKey: ["branch-settings", branchId],
    queryFn: async () => (await fbApi.settings()).data.data,
    enabled: Boolean(branchId),
  });

  const session = sessionQuery.data;
  const shift = shiftQuery.data;
  const locationId = shift?.location_id ?? locationsQuery.data?.[0]?.id;

  const allItems = useMemo(() => {
    if (!session) return [];
    return session.orders.flatMap((o) => o.status !== "cancelled" ? o.items.filter((i) => i.status !== "cancelled") : []);
  }, [session]);

  const subtotal = allItems.reduce((sum, i) => sum + i.unit_price * i.qty, 0);
  const totalAfterDiscount = Math.max(subtotal - discount, 0);
  const discountPercentage = subtotal > 0 ? (discount * 100) / subtotal : 0;
  const changeAmount = paymentMethod === "cash" ? Math.max(paidAmount - totalAfterDiscount, 0) : 0;
  const outstandingCount = allItems.filter((item) => item.status === "pending" || item.status === "cooking").length;
  const readyNotServedCount = allItems.filter((item) => item.status === "done").length;
  const isDineIn = Boolean(session?.table_name);
  const sourceSummary = useMemo(() => {
    if (!session) return "";
    return [...new Set(session.orders.map((order) => order.source).filter(Boolean))].join(", ");
  }, [session]);

  const quickAmounts = useMemo(() => {
    const ceil100 = Math.ceil(totalAfterDiscount / 100) * 100;
    const ceil500 = Math.ceil(totalAfterDiscount / 500) * 500;
    const ceil1000 = Math.ceil(totalAfterDiscount / 1000) * 1000;
    return [...new Set([totalAfterDiscount, ceil100, ceil500, ceil1000])];
  }, [totalAfterDiscount]);
  const paymentReference = creditRef.trim();
  const receiptPrintedAt = useMemo(
    () => new Date().toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" }),
    [checkoutResult]
  );
  const uploadedQrUrl = branchSettingsQuery.data?.promptpay_qr_url ?? null;
  const hasDynamicPromptPayTarget = Boolean(branchSettingsQuery.data?.promptpay_target);
  const promptpayConfigured = Boolean(uploadedQrUrl || hasDynamicPromptPayTarget);

  const paymentQrQuery = useQuery({
    queryKey: ["session-payment-qr", sessionId, totalAfterDiscount],
    queryFn: async () => {
      const response = await authApi.get(`/restaurant/sessions/${sessionId}/payment-qr`, {
        params: { amount: totalAfterDiscount.toFixed(2) },
      });
      const result = response.data.data as { payload: string; amount: string; promptpay_name: string | null };
      const dataUrl = await QRCode.toDataURL(result.payload, { width: 320, margin: 1 });
      return { ...result, dataUrl };
    },
    enabled: Boolean(sessionId && hasDynamicPromptPayTarget && !uploadedQrUrl && totalAfterDiscount > 0 && !checkoutResult),
    retry: false,
  });
  const paymentQrSrc = uploadedQrUrl || paymentQrQuery.data?.dataUrl || null;
  const paymentQrName = paymentQrQuery.data?.promptpay_name || branchSettingsQuery.data?.promptpay_name || null;
  const receiptLogoSrc = branchSettingsQuery.data?.receipt_show_logo
    ? branchSettingsQuery.data.receipt_logo_url
    : null;

  useEffect(() => {
    setPaymentQrImageLoaded(false);
  }, [paymentQrSrc]);

  useEffect(() => {
    setReceiptLogoLoaded(!receiptLogoSrc);
  }, [receiptLogoSrc]);

  useEffect(() => {
    if (
      searchParams.get("printBill") !== "1"
      || autoPrintStartedRef.current
      || !session
      || !promptpayConfigured
      || !paymentQrSrc
      || !paymentQrImageLoaded
      || !receiptLogoLoaded
      || checkoutResult
    ) return;

    autoPrintStartedRef.current = true;
    setPaymentMethod("promptpay");
    const timer = window.setTimeout(() => window.print(), 350);
    return () => window.clearTimeout(timer);
  }, [checkoutResult, paymentQrImageLoaded, paymentQrSrc, promptpayConfigured, receiptLogoLoaded, searchParams, session]);

  const checkoutPayload = useMemo(() => ({
        // ส่ง shift_id และ location_id แบบ optional — backend auto-detect ถ้าไม่มี
        shift_id: shift?.id ?? null,
        location_id: locationId ?? null,
        payment_method: paymentMethod,
        paid_amount: paymentMethod === "cash" ? paidAmount : totalAfterDiscount,
        payments: creditRef.trim()
          ? [{ payment_method: paymentMethod, amount: totalAfterDiscount, reference_no: creditRef.trim() }]
          : [],
        discount_amount: discount,
        customer_name: session?.customer_name ?? null,
        customer_phone: session?.customer_phone ?? null,
  }), [creditRef, discount, locationId, paidAmount, paymentMethod, session?.customer_name, session?.customer_phone, shift?.id, totalAfterDiscount]);

  const checkoutMutation = useMutation({
    mutationFn: async (approvalToken?: string) => {
      const res = await authApi.post(`/restaurant/sessions/${sessionId}/checkout`, {
        ...checkoutPayload,
        ...(approvalToken ? { approval_token: approvalToken } : {}),
      });
      return res.data.data as CheckoutResult;
    },
    onSuccess: (result) => {
      setCheckoutResult(result);
      queryClient.invalidateQueries({ queryKey: ["dining-tables"] });
      queryClient.invalidateQueries({ queryKey: ["dining-session"] });
      queryClient.invalidateQueries({ queryKey: ["fb-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["pickup-queue"] });
      toast({ title: `ชำระเงินสำเร็จ — ${result.order_number}` });
    },
    onError: (error) => toast({
      title: "ชำระเงินไม่สำเร็จ",
      description: errorMessage(error, "กรุณาลองใหม่อีกครั้ง")
    }),
  });

  const canApplyDiscount = (
    branchSettingsQuery.data?.pos_allow_discount ?? true
  ) && (
    hasPermission("pos.discount.apply") || hasPermission("pos.discount.override")
  );
  const canOverrideDiscount = hasPermission("pos.discount.override");
  const cashierDiscountLimit = branchSettingsQuery.data?.pos_cashier_discount_limit_pct ?? 10;
  const hardMaxDiscountPercentage = branchSettingsQuery.data?.pos_max_discount_pct ?? 100;
  const hardMaxDiscountAmount = (subtotal * hardMaxDiscountPercentage) / 100;

  function handleCheckout(): void {
    if (discountPercentage > cashierDiscountLimit && !canOverrideDiscount) {
      setManagerApprovalOpen(true);
      return;
    }
    checkoutMutation.mutate(undefined);
  }

  const canCheckout =
    allItems.length > 0 &&
    (paymentMethod !== "cash" || paidAmount >= totalAfterDiscount) &&
    !checkoutMutation.isPending;

  // ── Receipt View ──────────────────────────────────────────────────────────
  if (checkoutResult) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 p-4">
        <style>{`
          @media print {
            body { background: white !important; }
            body * { visibility: hidden !important; }
            .restaurant-print-receipt, .restaurant-print-receipt * { visibility: visible !important; }
            .restaurant-print-receipt {
              position: fixed !important;
              inset: 0 auto auto 0 !important;
              width: 80mm !important;
              max-width: 80mm !important;
              border: 0 !important;
              border-radius: 0 !important;
              box-shadow: none !important;
              padding: 4mm !important;
              color: #111827 !important;
              background: white !important;
              font-size: 11px !important;
              line-height: 1.3 !important;
            }
            .restaurant-print-actions { display: none !important; }
          }
        `}</style>
        <div className="w-full max-w-sm">
          <div className="rounded-3xl border border-emerald-200 bg-white p-8 shadow-lg text-center">
            <CheckCircle2 className="mx-auto h-16 w-16 text-emerald-500" />
            <h2 className="mt-4 text-2xl font-bold text-slate-900">ชำระเงินสำเร็จ</h2>
            <p className="mt-1 text-slate-500">{checkoutResult.order_number}</p>

            <div ref={receiptRef} className="restaurant-print-receipt mt-6 rounded-2xl border border-slate-200 p-4 text-left text-sm space-y-2">
              <div className="border-b border-dashed border-slate-300 pb-3 text-center">
                {receiptLogoSrc ? (
                  <img
                    src={receiptLogoSrc}
                    alt="โลโก้ร้าน"
                    className="mx-auto mb-2 h-32 max-w-80 object-contain grayscale contrast-200"
                    onLoad={() => setReceiptLogoLoaded(true)}
                    onError={() => setReceiptLogoLoaded(true)}
                  />
                ) : null}
                <p className="text-base font-black text-slate-950">{branchSettingsQuery.data?.pos_receipt_header || "Restaurant POS Restaurant"}</p>
                <p className="mt-1 text-xs text-slate-500">ใบเสร็จรับเงิน</p>
                <p className="mt-1 text-xs text-slate-500">{receiptPrintedAt}</p>
              </div>

              <div className="space-y-1 border-b border-dashed border-slate-200 pb-3 text-xs text-slate-600">
                <div className="flex justify-between"><span>เลขที่</span><span>{checkoutResult.order_number}</span></div>
                <div className="flex justify-between"><span>ประเภท</span><span>{SOURCE_LABELS[checkoutResult.source_type] ?? checkoutResult.source_type}</span></div>
                {checkoutResult.table_name ? <div className="flex justify-between"><span>โต๊ะ</span><span>{checkoutResult.table_name}</span></div> : null}
                {checkoutResult.queue_number ? <div className="flex justify-between"><span>คิว</span><span>{String(checkoutResult.queue_number).padStart(3, "0")}</span></div> : null}
                {sourceSummary ? <div className="flex justify-between"><span>ช่องทางสั่ง</span><span>{sourceSummary}</span></div> : null}
                <div className="flex justify-between"><span>ลูกค้า</span><span>{checkoutResult.customer_name || "ลูกค้าทั่วไป"}</span></div>
                {checkoutResult.customer_phone ? <div className="flex justify-between"><span>เบอร์โทร</span><span>{checkoutResult.customer_phone}</span></div> : null}
              </div>

              <div className="space-y-2 border-b border-dashed border-slate-200 pb-3">
                {allItems.map((item) => (
                  <div key={item.id} className="grid grid-cols-[1fr_auto] gap-3">
                    <div>
                      <p className="font-medium text-slate-900">{item.product_name}</p>
                      <p className="text-xs text-slate-500">
                        {item.qty} × {formatThaiCurrency(item.unit_price)}
                      </p>
                      {item.special_request ? <p className="text-xs text-amber-600">{item.special_request}</p> : null}
                    </div>
                    <div className="text-right font-medium">{formatThaiCurrency(item.qty * item.unit_price)}</div>
                  </div>
                ))}
              </div>

              <div className="flex justify-between"><span>วิธีชำระ</span><span>{PAYMENT_LABELS[checkoutResult.payment_method] ?? checkoutResult.payment_method}</span></div>
              {paymentReference ? <div className="flex justify-between gap-3"><span>อ้างอิง</span><span className="text-right break-all">{paymentReference}</span></div> : null}
              <div className="flex justify-between"><span>ยอดรวม</span><span>{formatThaiCurrency(subtotal)}</span></div>
              {discount > 0 ? <div className="flex justify-between"><span>ส่วนลด</span><span>{formatThaiCurrency(discount)}</span></div> : null}
              <div className="flex justify-between font-bold text-base border-t border-slate-200 pt-2">
                <span>ยอดสุทธิ</span><span>{formatThaiCurrency(checkoutResult.total_amount)}</span>
              </div>
              <div className="flex justify-between"><span>รับเงิน</span><span>{formatThaiCurrency(checkoutResult.paid_amount)}</span></div>
              {checkoutResult.change_amount > 0 && (
                <div className="flex justify-between text-emerald-700 font-semibold">
                  <span>เงินทอน</span><span>{formatThaiCurrency(checkoutResult.change_amount)}</span>
                </div>
              )}
              {checkoutResult.note ? <p className="border-t border-dashed border-slate-200 pt-2 text-xs text-slate-500">{checkoutResult.note}</p> : null}
              <p className="border-t border-dashed border-slate-200 pt-3 text-center text-xs text-slate-500">{branchSettingsQuery.data?.pos_receipt_footer || "ขอบคุณที่ใช้บริการ"}</p>
            </div>

            <div className="restaurant-print-actions mt-6 flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => window.print()}>
                <Printer className="mr-2 h-4 w-4" /> พิมพ์ใบเสร็จ
              </Button>
              <Button className="flex-1 bg-slate-950 hover:bg-slate-800" onClick={() => navigate(isDineIn ? "/restaurant/tables" : "/restaurant/orders")}>
                {isDineIn ? "กลับแผนที่โต๊ะ" : "กลับออเดอร์"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Loading ────────────────────────────────────────────────────────────────
  if (sessionQuery.isLoading) {
    return <div className="flex min-h-screen items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  if (!session) {
    return <div className="p-8 text-center text-slate-500">ไม่พบ session</div>;
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <style>{`
        @media print {
          body { background: white !important; }
          body * { visibility: hidden !important; }
          .restaurant-print-bill, .restaurant-print-bill * { visibility: visible !important; }
          .restaurant-print-bill {
            display: block !important;
            position: fixed !important;
            inset: 0 auto auto 0 !important;
            width: 80mm !important;
            max-width: 80mm !important;
            padding: 4mm !important;
            color: #111827 !important;
            background: white !important;
            font-size: 11px !important;
            line-height: 1.3 !important;
          }
        }
      `}</style>

      <div className="restaurant-print-bill hidden space-y-2 text-sm">
        <div className="border-b border-dashed border-slate-300 pb-3 text-center">
          {receiptLogoSrc ? (
            <img
              src={receiptLogoSrc}
              alt="โลโก้ร้าน"
              className="mx-auto mb-2 h-32 max-w-80 object-contain grayscale contrast-200"
              onLoad={() => setReceiptLogoLoaded(true)}
              onError={() => setReceiptLogoLoaded(true)}
            />
          ) : null}
          <p className="text-base font-black">{branchSettingsQuery.data?.pos_receipt_header || "Restaurant POS Restaurant"}</p>
          <p className="mt-1 text-xs">ใบแจ้งยอด / QR ชำระเงิน</p>
          <p className="mt-1 text-xs">{receiptPrintedAt}</p>
        </div>
        <div className="space-y-1 border-b border-dashed border-slate-300 pb-3 text-xs">
          <div className="flex justify-between"><span>ประเภท</span><span>{isDineIn ? "โต๊ะ" : "รับเอง / กลับบ้าน"}</span></div>
          {session.table_name ? <div className="flex justify-between"><span>โต๊ะ</span><span>{session.table_name}</span></div> : null}
          {session.queue_number ? <div className="flex justify-between"><span>คิว</span><span>{String(session.queue_number).padStart(3, "0")}</span></div> : null}
          <div className="flex justify-between"><span>ลูกค้า</span><span>{session.customer_name || "ลูกค้าทั่วไป"}</span></div>
        </div>
        <div className="space-y-2 border-b border-dashed border-slate-300 pb-3">
          {allItems.map((item) => (
            <div key={item.id} className="grid grid-cols-[1fr_auto] gap-3">
              <div>
                <p className="font-medium">{item.product_name}</p>
                <p className="text-xs">{item.qty} × {formatThaiCurrency(item.unit_price)}</p>
              </div>
              <span className="font-medium">{formatThaiCurrency(item.qty * item.unit_price)}</span>
            </div>
          ))}
        </div>
        <div className="space-y-1">
          <div className="flex justify-between"><span>ยอดรวม</span><span>{formatThaiCurrency(subtotal)}</span></div>
          {discount > 0 ? <div className="flex justify-between"><span>ส่วนลด</span><span>-{formatThaiCurrency(discount)}</span></div> : null}
          <div className="flex justify-between border-t border-slate-300 pt-2 text-base font-black">
            <span>ยอดชำระ</span><span>{formatThaiCurrency(totalAfterDiscount)}</span>
          </div>
        </div>
        {paymentQrSrc ? (
          <div className="border-t border-dashed border-slate-300 pt-3 text-center">
            <p className="font-bold">สแกน QR เพื่อชำระเงิน</p>
            <img
              src={paymentQrSrc}
              alt="QR PromptPay ชำระเงิน"
              className="mx-auto mt-2 h-48 w-48 object-contain"
              onLoad={() => setPaymentQrImageLoaded(true)}
            />
            <p className="mt-1 text-sm font-black">{formatThaiCurrency(totalAfterDiscount)}</p>
            {paymentQrName ? <p className="text-xs">ชื่อบัญชี {paymentQrName}</p> : null}
            {uploadedQrUrl ? <p className="mt-1 text-[10px]">กรุณาตรวจยอดก่อนยืนยันการชำระ</p> : null}
          </div>
        ) : null}
        <p className="border-t border-dashed border-slate-300 pt-3 text-center text-xs">
          {branchSettingsQuery.data?.pos_receipt_footer || "ขอบคุณที่ใช้บริการ"}
        </p>
      </div>

      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-6 py-4 flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-xl font-bold text-slate-900">
            รวมบิล {session.table_name ? `— โต๊ะ ${session.table_name}` : ""}
            {session.queue_number ? ` — คิว ${String(session.queue_number).padStart(3, "0")}` : ""}
          </h1>
          <p className="text-sm text-slate-500">
            {session.customer_name ?? "ไม่ระบุชื่อลูกค้า"}
            {session.customer_phone ? ` • ${session.customer_phone}` : ""}
          </p>
        </div>
        <div className="ml-auto">
          <ReceiptText className="h-6 w-6 text-orange-400" />
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-6 p-6 xl:flex-row">
        {/* Order Summary */}
        <div className="flex-1">
          <h2 className="mb-3 font-semibold text-slate-800">รายการที่สั่ง</h2>
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-3 text-left">เมนู</th>
                  <th className="px-4 py-3 text-center">จำนวน</th>
                  <th className="px-4 py-3 text-right">ราคา</th>
                  <th className="px-4 py-3 text-right">รวม</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {allItems.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">{item.product_name}</p>
                      {item.special_request && (
                        <p className="mt-0.5 text-xs text-amber-600">⚠️ {item.special_request}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center text-slate-600">{item.qty}</td>
                    <td className="px-4 py-3 text-right text-slate-600">{formatThaiCurrency(item.unit_price)}</td>
                    <td className="px-4 py-3 text-right font-medium text-slate-900">{formatThaiCurrency(item.unit_price * item.qty)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="border-t-2 border-slate-200 bg-slate-50">
                <tr>
                  <td colSpan={3} className="px-4 py-3 text-right font-semibold">ยอดรวม</td>
                  <td className="px-4 py-3 text-right font-bold text-slate-900">{formatThaiCurrency(subtotal)}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          {!shift && (
            <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <p className="font-medium">⚠️ ยังไม่มีกะที่เปิดอยู่</p>
              <p className="mt-1 text-xs">ระบบจะสร้างกะ F&B อัตโนมัติให้เมื่อชำระเงิน หรือเปิดกะที่หน้า POS ก่อนก็ได้</p>
            </div>
          )}
          {outstandingCount > 0 && (
            <div className="mt-4 rounded-2xl border border-orange-200 bg-orange-50 px-4 py-3 text-sm text-orange-800">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="font-bold">ยังมี {outstandingCount} รายการที่ครัวยังทำไม่เสร็จ</p>
                  <p className="mt-1 text-xs">ถ้าปิดบิลตอนนี้ session จะถูกปิด แต่รายการครัวอาจยังไม่พร้อมเสิร์ฟ</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={() => navigate(`/restaurant/session/${sessionId}/detail`)}>
                      ดูรายการในโต๊ะ
                    </Button>
                    <Button size="sm" className="bg-slate-950 hover:bg-slate-800" onClick={() => navigate("/restaurant/kitchen")}>
                      <ChefHat className="mr-1 h-4 w-4" />
                      ดูครัว
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
          {outstandingCount === 0 && readyNotServedCount > 0 && (
            <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              <p className="font-bold">มี {readyNotServedCount} รายการพร้อมเสิร์ฟแต่ยังไม่ mark served</p>
              <p className="mt-1 text-xs">ชำระได้ แต่ควรตรวจการเสิร์ฟก่อนปิดโต๊ะหากร้านต้องการ track served status</p>
            </div>
          )}
        </div>

        {/* Payment Panel */}
        <div className="w-full xl:w-96">
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-5">
            <h2 className="font-semibold text-slate-800">ชำระเงิน</h2>

            {/* Discount */}
            <div>
              <Label className="text-xs text-slate-500">ส่วนลด (บาท)</Label>
              <Input type="number" className="mt-1" value={discount} min={0} max={hardMaxDiscountAmount}
                disabled={!canApplyDiscount}
                onChange={(e) => setDiscount(Math.min(Number(e.target.value), hardMaxDiscountAmount))} />
            </div>

            {/* Total */}
            <div className="rounded-2xl bg-slate-950 px-5 py-4 text-white">
              <p className="text-xs uppercase tracking-wider text-slate-300">ยอดสุทธิ</p>
              <p className="mt-1 text-3xl font-black">{formatThaiCurrency(totalAfterDiscount)}</p>
            </div>

            <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-center">
              {!promptpayConfigured ? (
                <div className="text-left text-sm text-amber-800">
                  <p className="font-bold">ยังไม่ได้ตั้งค่าบัญชี PromptPay</p>
                  <p className="mt-1 text-xs">กรุณาตั้งค่าเบอร์มือถือหรือเลขผู้เสียภาษีของสาขาก่อนพิมพ์บิล QR</p>
                  {branchId ? (
                    <Button className="mt-3" size="sm" variant="outline" onClick={() => navigate(`/branches/${branchId}/settings`)}>
                      ไปตั้งค่า PromptPay
                    </Button>
                  ) : null}
                </div>
              ) : paymentQrQuery.isLoading ? (
                <div className="flex items-center justify-center gap-2 py-8 text-sm text-blue-700">
                  <Loader2 className="h-5 w-5 animate-spin" /> กำลังสร้าง QR ตามยอด
                </div>
              ) : paymentQrQuery.isError ? (
                <div className="text-sm text-rose-700">
                  <p className="font-bold">สร้าง QR ชำระเงินไม่สำเร็จ</p>
                  <Button className="mt-3" size="sm" variant="outline" onClick={() => paymentQrQuery.refetch()}>ลองใหม่</Button>
                </div>
              ) : paymentQrSrc ? (
                <>
                  <img
                    src={paymentQrSrc}
                    alt="QR PromptPay ชำระเงิน"
                    className="mx-auto h-44 w-44 object-contain"
                    onLoad={() => setPaymentQrImageLoaded(true)}
                  />
                  <p className="mt-2 text-sm font-bold text-slate-900">
                    {uploadedQrUrl ? "QR ที่แนบไว้" : "PromptPay"} · {formatThaiCurrency(totalAfterDiscount)}
                  </p>
                  {paymentQrName ? <p className="mt-1 text-xs text-slate-500">{paymentQrName}</p> : null}
                  {uploadedQrUrl ? <p className="mt-1 text-xs text-amber-700">QR จากรูปอาจไม่ใส่ยอดอัตโนมัติ กรุณาตรวจยอดตามบิล</p> : null}
                  <Button className="mt-3 w-full" variant="outline" disabled={!paymentQrImageLoaded} onClick={() => window.print()}>
                    <Printer className="mr-2 h-4 w-4" /> พิมพ์บิลพร้อม QR
                  </Button>
                </>
              ) : null}
            </div>

            {/* Payment Method */}
            <div>
              <Label className="text-xs text-slate-500">วิธีชำระเงิน</Label>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {(["cash", "promptpay", "credit_card", "bank_transfer", "other"] as PaymentMethod[]).map((m) => (
                  <button key={m} type="button"
                    onClick={() => setPaymentMethod(m)}
                    className={`rounded-xl border px-3 py-2 text-xs font-medium transition-all ${paymentMethod === m ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"}`}>
                    {PAYMENT_LABELS[m]}
                  </button>
                ))}
              </div>
            </div>

            {/* Cash Input */}
            {paymentMethod === "cash" && (
              <div className="space-y-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                <div>
                  <Label className="text-xs text-slate-600">รับเงิน (บาท)</Label>
                  <Input type="number" className="mt-1 h-12 text-right text-xl font-bold"
                    value={paidAmount} onChange={(e) => setPaidAmount(Number(e.target.value))} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {quickAmounts.map((v) => (
                    <button key={v} type="button"
                      onClick={() => setPaidAmount(v)}
                      className="rounded-xl border border-slate-300 bg-white py-2 text-sm hover:bg-slate-50">
                      {formatThaiCurrency(v)}
                    </button>
                  ))}
                </div>
                <div className={`rounded-xl px-4 py-3 text-lg font-bold ${paidAmount >= totalAfterDiscount ? "bg-emerald-100 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                  {paidAmount >= totalAfterDiscount
                    ? `เงินทอน ${formatThaiCurrency(changeAmount)}`
                    : `ยังขาด ${formatThaiCurrency(totalAfterDiscount - paidAmount)}`}
                </div>
              </div>
            )}

            {/* Reference for non-cash methods */}
            {(paymentMethod === "promptpay" || paymentMethod === "credit_card" || paymentMethod === "bank_transfer") && (
              <div>
                <Label className="text-xs text-slate-500">เลขอ้างอิง (ไม่บังคับ)</Label>
                <Input className="mt-1" value={creditRef} onChange={(e) => setCreditRef(e.target.value)}
                  placeholder={paymentMethod === "credit_card" ? "เลขอ้างอิงบัตร" : paymentMethod === "promptpay" ? "เลขอ้างอิง PromptPay" : "เลขอ้างอิงการโอน"} />
              </div>
            )}

            {/* Checkout Button */}
            <Button
              className="h-14 w-full rounded-2xl bg-emerald-600 text-lg font-bold hover:bg-emerald-700 disabled:opacity-50"
              disabled={!canCheckout}
              onClick={handleCheckout}
            >
              {checkoutMutation.isPending
                ? <Loader2 className="h-6 w-6 animate-spin" />
                : `ชำระเงิน ${formatThaiCurrency(totalAfterDiscount)}`}
            </Button>
          </div>
        </div>
      </div>
      {managerApprovalOpen && sessionId ? (
        <ManagerApprovalDialog
          open
          onOpenChange={setManagerApprovalOpen}
          action="pos.discount.override"
          requestPayload={{ session_id: sessionId, ...checkoutPayload }}
          reason={`ส่วนลด ${discountPercentage.toFixed(2)}% เกินเพดาน Cashier ${cashierDiscountLimit.toFixed(2)}%`}
          description="ส่วนลดของ Restaurant checkout นี้ต้องได้รับอนุมัติจาก Manager"
          onApproved={async (token) => {
            await checkoutMutation.mutateAsync(token);
          }}
        />
      ) : null}
    </div>
  );
}
