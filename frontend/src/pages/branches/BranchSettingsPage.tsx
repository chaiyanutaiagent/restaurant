import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { ArrowLeft, ImagePlus, Loader2, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import ReceiptView from "@/pages/pos/ReceiptView";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import { branchApi } from "@/lib/adminApi";
import { productApi } from "@/lib/productApi";
import { useAuthStore } from "@/stores/auth.store";
import type { BranchReplacementRule, BranchSettings } from "@/types/admin";
import type { ProductListItem } from "@/types/product";
import type { SaleOrder } from "@/types/pos";

const sampleReceipt: SaleOrder = {
  id: "sample-order",
  order_number: "SO-20260514-001",
  status: "completed",
  branch_id: "sample-branch",
  location_id: "sample-location",
  shift_id: "sample-shift",
  user_id: "sample-user",
  customer_name: "ลูกค้าทั่วไป",
  customer_phone: null,
  subtotal: 100,
  discount_amount: 0,
  vat_amount: 7,
  total_amount: 107,
  paid_amount: 107,
  change_amount: 0,
  is_offline: false,
  note: null,
  created_at: new Date().toISOString(),
  items: [
    {
      id: "line-1",
      product_id: "product-1",
      variant_id: null,
      product_name: "สินค้าตัวอย่าง",
      variant_name: null,
      sku: "SKU-001",
      unit_code: "PCS",
      qty: 1,
      unit_price: 100,
      original_price: 100,
      discount_amount: 0,
      vat_type: "inclusive",
      vat_rate: 7,
      vat_amount: 7,
      subtotal: 100
    }
  ],
  payments: [
    {
      id: "payment-1",
      payment_method: "promptpay",
      amount: 107,
      reference_no: null,
      paid_at: new Date().toISOString()
    }
  ]
};

type BranchFormState = {
  name: string;
  name_en: string;
  address: string;
  landmark: string;
  phone: string;
  email: string;
  latitude: string;
  longitude: string;
  google_maps_url: string;
  is_warehouse: boolean;
  is_active: boolean;
  sort_order: number;
};

type SettingsFormState = {
  pos_receipt_header: string;
  pos_receipt_footer: string;
  pos_require_customer: boolean;
  pos_allow_discount: boolean;
  pos_max_discount_pct: number;
  pos_cashier_discount_limit_pct: number;
  stock_adjust_approval_threshold_qty: number;
  promptpay_target: string;
  promptpay_name: string;
  promptpay_qr_url: string;
  public_storefront_enabled: boolean;
  allow_negative_stock: boolean;
  low_stock_alert_enabled: boolean;
  notify_low_stock_email: string;
  receipt_show_tax_id: boolean;
  receipt_show_logo: boolean;
  receipt_logo_url: string;
  receipt_copies: number;
};

function settingsToForm(settings: BranchSettings | null | undefined): SettingsFormState {
  return {
    pos_receipt_header: settings?.pos_receipt_header ?? "",
    pos_receipt_footer: settings?.pos_receipt_footer ?? "ขอบคุณที่ใช้บริการ",
    pos_require_customer: settings?.pos_require_customer ?? false,
    pos_allow_discount: settings?.pos_allow_discount ?? true,
    pos_max_discount_pct: settings?.pos_max_discount_pct ?? 100,
    pos_cashier_discount_limit_pct: settings?.pos_cashier_discount_limit_pct ?? 10,
    stock_adjust_approval_threshold_qty: settings?.stock_adjust_approval_threshold_qty ?? 10,
    promptpay_target: settings?.promptpay_target ?? "",
    promptpay_name: settings?.promptpay_name ?? "",
    promptpay_qr_url: settings?.promptpay_qr_url ?? "",
    public_storefront_enabled: settings?.public_storefront_enabled ?? true,
    allow_negative_stock: settings?.allow_negative_stock ?? false,
    low_stock_alert_enabled: settings?.low_stock_alert_enabled ?? true,
    notify_low_stock_email: settings?.notify_low_stock_email ?? "",
    receipt_show_tax_id: settings?.receipt_show_tax_id ?? true,
    receipt_show_logo: settings?.receipt_show_logo ?? false,
    receipt_logo_url: settings?.receipt_logo_url ?? "",
    receipt_copies: settings?.receipt_copies ?? 1
  };
}

function getErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    if (typeof response?.data?.detail === "string") return response.data.detail;
  }
  return error instanceof Error ? error.message : "ทำรายการไม่สำเร็จ";
}

export default function BranchSettingsPage(): JSX.Element {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const canEdit = hasPermission("system.branch.edit");

  const [branchForm, setBranchForm] = useState<BranchFormState | null>(null);
  const [settingsForm, setSettingsForm] = useState<SettingsFormState | null>(null);
  const [qrPreview, setQrPreview] = useState<string | null>(null);
  const [qrPreviewError, setQrPreviewError] = useState<string | null>(null);
  const [qrPreviewLoading, setQrPreviewLoading] = useState(false);
  const [sourceSearch, setSourceSearch] = useState("");
  const [replacementSearch, setReplacementSearch] = useState("");
  const [selectedSourceProduct, setSelectedSourceProduct] = useState<ProductListItem | null>(null);
  const [selectedReplacementProduct, setSelectedReplacementProduct] = useState<ProductListItem | null>(null);

  const branchQuery = useQuery({
    queryKey: ["admin", "branch", id],
    enabled: Boolean(id),
    queryFn: async () => (await branchApi.get(id)).data.data
  });

  const settingsQuery = useQuery({
    queryKey: ["admin", "branch-settings", id],
    enabled: Boolean(id),
    queryFn: async () => (await branchApi.getSettings(id)).data.data
  });

  const myBranchesQuery = useQuery({
    queryKey: ["system", "my-branches"],
    queryFn: async () => (await authApi.myBranches()).data.data
  });
  const replacementRulesQuery = useQuery({
    queryKey: ["admin", "branch-replacement-rules", id],
    enabled: Boolean(id),
    queryFn: async () => (await branchApi.listReplacementRules(id)).data.data as BranchReplacementRule[]
  });
  const sourceProductsQuery = useQuery({
    queryKey: ["admin", "branch-replacement-source-search", sourceSearch],
    enabled: sourceSearch.trim().length >= 2,
    queryFn: async () => {
      const response = await productApi.list({ search: sourceSearch.trim(), is_active: true, page: 1, limit: 12 });
      return response.data.data as ProductListItem[];
    }
  });
  const replacementProductsQuery = useQuery({
    queryKey: ["admin", "branch-replacement-target-search", replacementSearch],
    enabled: replacementSearch.trim().length >= 2,
    queryFn: async () => {
      const response = await productApi.list({ search: replacementSearch.trim(), is_active: true, page: 1, limit: 12 });
      return response.data.data as ProductListItem[];
    }
  });

  const canAccessBranch = useMemo(() => {
    if (canEdit) {
      return true;
    }
    return (myBranchesQuery.data ?? []).some((branch) => branch.branch_id === id);
  }, [canEdit, id, myBranchesQuery.data]);

  useEffect(() => {
    if (branchQuery.data) {
      setBranchForm({
        name: branchQuery.data.name,
        name_en: branchQuery.data.name_en ?? "",
        address: branchQuery.data.address ?? "",
        landmark: branchQuery.data.landmark ?? "",
        phone: branchQuery.data.phone ?? "",
        email: branchQuery.data.email ?? "",
        latitude: branchQuery.data.latitude?.toString() ?? "",
        longitude: branchQuery.data.longitude?.toString() ?? "",
        google_maps_url: branchQuery.data.google_maps_url ?? "",
        is_warehouse: branchQuery.data.is_warehouse,
        is_active: branchQuery.data.is_active,
        sort_order: branchQuery.data.sort_order
      });
    }
  }, [branchQuery.data]);

  useEffect(() => {
    if (settingsQuery.data) {
      setSettingsForm(settingsToForm(settingsQuery.data));
    }
  }, [settingsQuery.data]);

  useEffect(() => {
    let cancelled = false;
    const run = async (): Promise<void> => {
      const target = settingsForm?.promptpay_target.trim() ?? "";
      setQrPreview(null);
      setQrPreviewError(null);
      if (!target) {
        setQrPreviewLoading(false);
        return;
      }
      setQrPreviewLoading(true);
      try {
        const payloadResponse = await fetch(`/api/v1/pos/promptpay/qr?target=${encodeURIComponent(target)}`);
        const payloadJson = await payloadResponse.json() as { data?: { payload?: string }; detail?: string };
        if (!payloadResponse.ok) {
          throw new Error(payloadJson.detail || "ข้อมูล PromptPay ไม่ถูกต้อง");
        }
        const payload = payloadJson.data?.payload;
        if (!payload) {
          throw new Error("สร้างตัวอย่าง QR ไม่สำเร็จ");
        }
        const dataUrl = await QRCode.toDataURL(payload);
        if (!cancelled) {
          setQrPreview(dataUrl);
        }
      } catch (error) {
        if (!cancelled) {
          setQrPreviewError(getErrorMessage(error));
        }
      } finally {
        if (!cancelled) {
          setQrPreviewLoading(false);
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [settingsForm?.promptpay_target]);

  const saveBranchMutation = useMutation({
    mutationFn: async () => {
      if (!branchForm) {
        throw new Error("ยังไม่มีข้อมูลสาขา");
      }
      return branchApi.update(id, {
        ...branchForm,
        latitude: branchForm.latitude.trim() ? Number(branchForm.latitude) : null,
        longitude: branchForm.longitude.trim() ? Number(branchForm.longitude) : null,
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "branch", id] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "branches"] })
      ]);
      toast({ title: "บันทึกข้อมูลสาขาแล้ว" });
    }
  });

  const saveSettingsMutation = useMutation({
    mutationFn: async (payload: Partial<SettingsFormState>) => branchApi.updateSettings(id, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "branch-settings", id] });
      toast({ title: "บันทึกการตั้งค่าแล้ว" });
    },
    onError: (error) => {
      toast({ title: "บันทึกการตั้งค่าไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    }
  });
  const uploadPromptPayQrMutation = useMutation({
    mutationFn: async (file: File) => branchApi.uploadPromptPayQr(id, file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "branch-settings", id] });
      toast({ title: "แนบรูป QR แล้ว" });
    },
    onError: (error) => {
      toast({ title: "แนบรูป QR ไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    }
  });
  const deletePromptPayQrMutation = useMutation({
    mutationFn: async () => branchApi.deletePromptPayQr(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "branch-settings", id] });
      toast({ title: "ลบรูป QR แล้ว" });
    },
    onError: (error) => {
      toast({ title: "ลบรูป QR ไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    }
  });
  const uploadReceiptLogoMutation = useMutation({
    mutationFn: async (file: File) => branchApi.uploadReceiptLogo(id, file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "branch-settings", id] });
      toast({ title: "แนบโลโก้ร้านแล้ว" });
    },
    onError: (error) => {
      toast({ title: "แนบโลโก้ไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    }
  });
  const deleteReceiptLogoMutation = useMutation({
    mutationFn: async () => branchApi.deleteReceiptLogo(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "branch-settings", id] });
      toast({ title: "ลบโลโก้ร้านแล้ว" });
    },
    onError: (error) => {
      toast({ title: "ลบโลโก้ไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    }
  });
  const saveReplacementRuleMutation = useMutation({
    mutationFn: async () => {
      if (!selectedSourceProduct || !selectedReplacementProduct) {
        throw new Error("กรุณาเลือกสินค้าต้นทางและสินค้าทดแทน");
      }
      return branchApi.upsertReplacementRule(id, {
        source_product_id: selectedSourceProduct.id,
        replacement_product_id: selectedReplacementProduct.id
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "branch-replacement-rules", id] });
      setSelectedSourceProduct(null);
      setSelectedReplacementProduct(null);
      setSourceSearch("");
      setReplacementSearch("");
      toast({ title: "บันทึกกฎสินค้าทดแทนส่วนกลางแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "บันทึกกฎไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });
  const deleteReplacementRuleMutation = useMutation({
    mutationFn: async (sourceProductId: string) => branchApi.deleteReplacementRule(id, sourceProductId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "branch-replacement-rules", id] });
      toast({ title: "ลบกฎสินค้าทดแทนแล้ว" });
    },
    onError: (error: Error) => {
      toast({ title: "ลบกฎไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  if (!canAccessBranch && !myBranchesQuery.isLoading) {
    return <Navigate to="/403" replace />;
  }

  const branch = branchQuery.data;
  const settings = settingsForm;

  return (
    <div className="space-y-6">
      <PageHeader
        title={branch ? `${branch.name} — ตั้งค่า` : "ตั้งค่าสาขา"}
        subtitle="จัดการข้อมูลสาขา, POS, PromptPay, สต็อก และใบเสร็จ"
        actions={
          <Button variant="outline" onClick={() => navigate("/branches")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            กลับ
          </Button>
        }
      />

      <Tabs defaultValue="info">
        <TabsList className="flex h-auto flex-wrap gap-1">
          <TabsTrigger value="info">ข้อมูลสาขา</TabsTrigger>
          <TabsTrigger value="pos">ตั้งค่า POS</TabsTrigger>
          <TabsTrigger value="promptpay">PromptPay</TabsTrigger>
          <TabsTrigger value="stock">สต็อก</TabsTrigger>
          <TabsTrigger value="receipt">ใบเสร็จ</TabsTrigger>
          <TabsTrigger value="replacement">สินค้าทดแทน</TabsTrigger>
        </TabsList>

        <TabsContent value="info">
          <Card>
            <CardContent className="grid gap-4 p-5">
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Code">
                  <Input value={branch?.code ?? ""} readOnly />
                </Field>
                <Field label="ชื่อสาขา">
                  <Input
                    value={branchForm?.name ?? ""}
                    onChange={(event) => setBranchForm((prev) => prev ? { ...prev, name: event.target.value } : prev)}
                  />
                </Field>
              </div>
              <Field label="ชื่อภาษาอังกฤษ">
                <Input
                  value={branchForm?.name_en ?? ""}
                  onChange={(event) => setBranchForm((prev) => prev ? { ...prev, name_en: event.target.value } : prev)}
                />
              </Field>
              <Field label="ที่อยู่">
                <textarea
                  className="min-h-24 rounded-md border border-gray-200 px-3 py-2 text-sm"
                  value={branchForm?.address ?? ""}
                  onChange={(event) => setBranchForm((prev) => prev ? { ...prev, address: event.target.value } : prev)}
                />
              </Field>
              <Field label="จุดสังเกต">
                <Input
                  value={branchForm?.landmark ?? ""}
                  onChange={(event) => setBranchForm((prev) => prev ? { ...prev, landmark: event.target.value } : prev)}
                />
              </Field>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="โทรศัพท์">
                  <Input
                    value={branchForm?.phone ?? ""}
                    onChange={(event) => setBranchForm((prev) => prev ? { ...prev, phone: event.target.value } : prev)}
                  />
                </Field>
                <Field label="Email">
                  <Input
                    value={branchForm?.email ?? ""}
                    onChange={(event) => setBranchForm((prev) => prev ? { ...prev, email: event.target.value } : prev)}
                  />
                </Field>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Latitude">
                  <Input
                    value={branchForm?.latitude ?? ""}
                    onChange={(event) => setBranchForm((prev) => prev ? { ...prev, latitude: event.target.value } : prev)}
                    placeholder="13.7563309"
                  />
                </Field>
                <Field label="Longitude">
                  <Input
                    value={branchForm?.longitude ?? ""}
                    onChange={(event) => setBranchForm((prev) => prev ? { ...prev, longitude: event.target.value } : prev)}
                    placeholder="100.5017651"
                  />
                </Field>
              </div>
              <Field label="Google Maps URL">
                <Input
                  value={branchForm?.google_maps_url ?? ""}
                  onChange={(event) => setBranchForm((prev) => prev ? { ...prev, google_maps_url: event.target.value } : prev)}
                />
              </Field>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                <p className="font-medium text-slate-900">Store Locator readiness</p>
                <p className="mt-1">
                  {branchForm?.latitude && branchForm?.longitude
                    ? "สาขานี้มีพิกัดพร้อมนำไปแสดงบนแผนที่"
                    : "กรอก Latitude และ Longitude เพื่อให้สมาชิกค้นหาร้านบนแผนที่ได้"}
                </p>
                <p className="mt-2">
                  {settings?.public_storefront_enabled
                    ? "สถานะ: สาขานี้พร้อมเผยแพร่สู่ storefront/public API"
                    : "สถานะ: สาขานี้ถูกซ่อนจาก storefront/public API ชั่วคราว"}
                </p>
                {branchForm?.google_maps_url ? (
                  <a className="mt-2 inline-block text-blue-600 underline" href={branchForm.google_maps_url} target="_blank" rel="noreferrer">
                    เปิดลิงก์ Google Maps
                  </a>
                ) : null}
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <ToggleField
                  label="เป็นคลังสินค้า"
                  checked={branchForm?.is_warehouse ?? false}
                  onChange={(checked) => setBranchForm((prev) => prev ? { ...prev, is_warehouse: checked } : prev)}
                />
                <ToggleField
                  label="เปิดใช้งาน"
                  checked={branchForm?.is_active ?? true}
                  onChange={(checked) => setBranchForm((prev) => prev ? { ...prev, is_active: checked } : prev)}
                />
                <Field label="Sort Order">
                  <Input
                    type="number"
                    value={branchForm?.sort_order ?? 0}
                    onChange={(event) => setBranchForm((prev) => prev ? { ...prev, sort_order: Number(event.target.value || 0) } : prev)}
                  />
                </Field>
              </div>
              <div className="flex justify-end">
                <Button onClick={() => saveBranchMutation.mutate()} disabled={!canEdit}>
                  บันทึกข้อมูลสาขา
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pos">
          <Card>
            <CardContent className="grid gap-4 p-5">
              <Field label="Receipt Header">
                <textarea
                  className="min-h-24 rounded-md border border-gray-200 px-3 py-2 text-sm"
                  value={settings?.pos_receipt_header ?? ""}
                  onChange={(event) => setSettingsForm((prev) => prev ? { ...prev, pos_receipt_header: event.target.value } : prev)}
                />
              </Field>
              <Field label="Receipt Footer">
                <textarea
                  className="min-h-24 rounded-md border border-gray-200 px-3 py-2 text-sm"
                  value={settings?.pos_receipt_footer ?? ""}
                  onChange={(event) => setSettingsForm((prev) => prev ? { ...prev, pos_receipt_footer: event.target.value } : prev)}
                />
              </Field>
              <ToggleField
                label="บังคับกรอกข้อมูลลูกค้า"
                checked={settings?.pos_require_customer ?? false}
                onChange={(checked) => setSettingsForm((prev) => prev ? { ...prev, pos_require_customer: checked } : prev)}
              />
              <ToggleField
                label="อนุญาตส่วนลด"
                checked={settings?.pos_allow_discount ?? true}
                onChange={(checked) => setSettingsForm((prev) => prev ? { ...prev, pos_allow_discount: checked } : prev)}
              />
              <ToggleField
                label="แสดงสาขานี้ใน storefront / ส่งต่อ poolproject ภายหลัง"
                checked={settings?.public_storefront_enabled ?? true}
                onChange={(checked) => setSettingsForm((prev) => prev ? { ...prev, public_storefront_enabled: checked } : prev)}
              />
              <Field label="Max Discount %">
                <Input
                  type="number"
                  disabled={!settings?.pos_allow_discount}
                  min={0}
                  max={100}
                  value={settings?.pos_max_discount_pct ?? 100}
                  onChange={(event) => {
                    const maximum = Number(event.target.value || 0);
                    setSettingsForm((prev) => prev ? {
                      ...prev,
                      pos_max_discount_pct: maximum,
                      pos_cashier_discount_limit_pct: Math.min(
                        prev.pos_cashier_discount_limit_pct,
                        maximum
                      )
                    } : prev);
                  }}
                />
              </Field>
              <Field label="Cashier Discount Ceiling % (เกินกว่านี้ต้อง Manager อนุมัติ)">
                <Input
                  type="number"
                  disabled={!settings?.pos_allow_discount}
                  min={0}
                  max={settings?.pos_max_discount_pct ?? 100}
                  value={settings?.pos_cashier_discount_limit_pct ?? 10}
                  onChange={(event) => setSettingsForm((prev) => prev ? {
                    ...prev,
                    pos_cashier_discount_limit_pct: Number(event.target.value || 0)
                  } : prev)}
                />
              </Field>
              <div className="flex justify-end">
                <Button onClick={() => saveSettingsMutation.mutate(settings ?? {})} disabled={!canEdit}>
                  บันทึกตั้งค่า POS
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="promptpay">
          <Card>
            <CardContent className="grid gap-4 p-5 lg:grid-cols-[1.4fr_320px]">
              <div className="space-y-4">
                <Field label="เบอร์โทรศัพท์หรือเลขผู้เสียภาษี PromptPay">
                  <Input
                    value={settings?.promptpay_target ?? ""}
                    onChange={(event) => setSettingsForm((prev) => prev ? { ...prev, promptpay_target: event.target.value } : prev)}
                    inputMode="numeric"
                    placeholder="เช่น 0812345678 หรือเลขผู้เสียภาษี 13 หลัก"
                  />
                </Field>
                <p className="text-sm text-gray-500">
                  ตั้งค่าเฉพาะ {branch?.name ?? "สาขานี้"} — แนบรูป QR ของร้านได้ หรือกรอก PromptPay เพื่อให้ระบบสร้าง QR แบบระบุยอด
                </p>
                {qrPreviewError ? <p className="text-sm font-medium text-red-600">{qrPreviewError}</p> : null}
                <Field label="ชื่อบัญชี">
                  <Input
                    value={settings?.promptpay_name ?? ""}
                    onChange={(event) => setSettingsForm((prev) => prev ? { ...prev, promptpay_name: event.target.value } : prev)}
                    placeholder="ชื่อที่ต้องการแสดงใต้ QR"
                  />
                </Field>
                <Field label="แนบรูป QR ของร้าน">
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      id="promptpay-qr-upload"
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      disabled={!canEdit || uploadPromptPayQrMutation.isPending}
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) uploadPromptPayQrMutation.mutate(file);
                        event.currentTarget.value = "";
                      }}
                    />
                    <Button asChild variant="outline" disabled={!canEdit || uploadPromptPayQrMutation.isPending}>
                      <label htmlFor="promptpay-qr-upload" className="cursor-pointer">
                        {uploadPromptPayQrMutation.isPending
                          ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          : <ImagePlus className="mr-2 h-4 w-4" />}
                        {settings?.promptpay_qr_url ? "เปลี่ยนรูป QR" : "เลือกรูป QR"}
                      </label>
                    </Button>
                    {settings?.promptpay_qr_url ? (
                      <Button
                        type="button"
                        variant="outline"
                        className="text-red-600 hover:text-red-700"
                        disabled={!canEdit || deletePromptPayQrMutation.isPending}
                        onClick={() => deletePromptPayQrMutation.mutate()}
                      >
                        {deletePromptPayQrMutation.isPending
                          ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          : <Trash2 className="mr-2 h-4 w-4" />}
                        ลบรูป
                      </Button>
                    ) : null}
                  </div>
                  <p className="mt-2 text-xs text-gray-500">รองรับ PNG, JPG และ WebP รูปที่แนบจะถูกใช้บนบิลก่อน QR ที่ระบบสร้าง</p>
                </Field>
                <div className="flex justify-end">
                  <Button
                    onClick={() => saveSettingsMutation.mutate({
                      promptpay_target: settings?.promptpay_target.trim() ?? "",
                      promptpay_name: settings?.promptpay_name.trim() ?? "",
                    })}
                    disabled={!canEdit || qrPreviewLoading || Boolean(qrPreviewError)}
                  >
                    บันทึก PromptPay
                  </Button>
                </div>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <p className="mb-3 text-sm font-medium text-gray-900">Preview QR</p>
                {settings?.promptpay_qr_url ? (
                  <div className="text-center">
                    <span className="mb-2 inline-flex rounded-full bg-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-700">รูป QR ที่แนบ</span>
                    <img src={settings.promptpay_qr_url} alt="QR ชำระเงินที่แนบ" className="mx-auto w-full max-w-56 rounded-lg object-contain" />
                  </div>
                ) : qrPreview ? (
                  <img src={qrPreview} alt="PromptPay QR" className="mx-auto w-full max-w-56" />
                ) : (
                  <div className="flex h-56 items-center justify-center rounded-lg border border-dashed border-gray-300 px-4 text-center text-sm text-gray-500">
                    {qrPreviewLoading ? "กำลังสร้างตัวอย่าง QR..." : qrPreviewError ? "กรุณาตรวจสอบข้อมูล PromptPay" : "กรอก PromptPay เพื่อดูตัวอย่าง QR"}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="stock">
          <Card>
            <CardContent className="grid gap-4 p-5">
              <ToggleField
                label="Allow Negative Stock"
                checked={settings?.allow_negative_stock ?? false}
                warning={settings?.allow_negative_stock ? "เปิดให้จำนวนสินค้าติดลบได้ — ใช้ด้วยความระมัดระวัง" : undefined}
                danger={settings?.allow_negative_stock ?? false}
                onChange={(checked) => setSettingsForm((prev) => prev ? { ...prev, allow_negative_stock: checked } : prev)}
              />
              <ToggleField
                label="แจ้งเตือนสต็อกต่ำ"
                checked={settings?.low_stock_alert_enabled ?? true}
                onChange={(checked) => setSettingsForm((prev) => prev ? { ...prev, low_stock_alert_enabled: checked } : prev)}
              />
              <Field label="Email สำหรับแจ้งเตือน">
                <Input
                  value={settings?.notify_low_stock_email ?? ""}
                  onChange={(event) => setSettingsForm((prev) => prev ? { ...prev, notify_low_stock_email: event.target.value } : prev)}
                />
              </Field>
              <Field label="Stock Adjustment Threshold (เกินจำนวนนี้ต้อง Manager อนุมัติ)">
                <Input
                  type="number"
                  min={0}
                  step="0.0001"
                  value={settings?.stock_adjust_approval_threshold_qty ?? 10}
                  onChange={(event) => setSettingsForm((prev) => prev ? {
                    ...prev,
                    stock_adjust_approval_threshold_qty: Number(event.target.value || 0)
                  } : prev)}
                />
              </Field>
              <div className="flex justify-end">
                <Button onClick={() => saveSettingsMutation.mutate(settings ?? {})} disabled={!canEdit}>
                  บันทึกตั้งค่าสต็อก
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="receipt">
          <Card>
            <CardContent className="grid gap-6 p-5 lg:grid-cols-[1fr_380px]">
              <div className="space-y-4">
                <ToggleField
                  label="แสดงเลขผู้เสียภาษี"
                  checked={settings?.receipt_show_tax_id ?? true}
                  onChange={(checked) => setSettingsForm((prev) => prev ? { ...prev, receipt_show_tax_id: checked } : prev)}
                />
                <ToggleField
                  label="แสดงโลโก้"
                  checked={settings?.receipt_show_logo ?? false}
                  onChange={(checked) => setSettingsForm((prev) => prev ? { ...prev, receipt_show_logo: checked } : prev)}
                />
                <Field label="แนบโลโก้ร้านสำหรับหัวบิล">
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      id="receipt-logo-upload"
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      disabled={!canEdit || uploadReceiptLogoMutation.isPending}
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) uploadReceiptLogoMutation.mutate(file);
                        event.currentTarget.value = "";
                      }}
                    />
                    <Button asChild variant="outline" disabled={!canEdit || uploadReceiptLogoMutation.isPending}>
                      <label htmlFor="receipt-logo-upload" className="cursor-pointer">
                        {uploadReceiptLogoMutation.isPending
                          ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          : <ImagePlus className="mr-2 h-4 w-4" />}
                        {settings?.receipt_logo_url ? "เปลี่ยนโลโก้" : "เลือกโลโก้"}
                      </label>
                    </Button>
                    {settings?.receipt_logo_url ? (
                      <Button
                        type="button"
                        variant="outline"
                        className="text-red-600 hover:text-red-700"
                        disabled={!canEdit || deleteReceiptLogoMutation.isPending}
                        onClick={() => deleteReceiptLogoMutation.mutate()}
                      >
                        {deleteReceiptLogoMutation.isPending
                          ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          : <Trash2 className="mr-2 h-4 w-4" />}
                        ลบโลโก้
                      </Button>
                    ) : null}
                  </div>
                  <p className="mt-2 text-xs text-gray-500">รองรับ PNG, JPG และ WebP แนะนำพื้นหลังโปร่งใสหรือสีขาว</p>
                  {settings?.receipt_logo_url ? (
                    <div className="mt-3 rounded-xl border border-gray-200 bg-white p-3">
                      <img src={settings.receipt_logo_url} alt="โลโก้ร้าน" className="mx-auto h-48 max-w-[28rem] object-contain" />
                    </div>
                  ) : null}
                </Field>
                <Field label="จำนวนสำเนา">
                  <select
                    className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                    value={settings?.receipt_copies ?? 1}
                    onChange={(event) => setSettingsForm((prev) => prev ? { ...prev, receipt_copies: Number(event.target.value) } : prev)}
                  >
                    <option value={1}>1</option>
                    <option value={2}>2</option>
                    <option value={3}>3</option>
                  </select>
                </Field>
                <div className="flex justify-end">
                  <Button onClick={() => saveSettingsMutation.mutate(settings ?? {})} disabled={!canEdit}>
                    บันทึกตั้งค่าใบเสร็จ
                  </Button>
                </div>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <p className="mb-3 text-sm font-medium text-gray-900">Preview receipt</p>
                <div className="overflow-auto rounded-lg bg-white">
                  <ReceiptView
                    order={sampleReceipt}
                    company={{
                      name: branch?.name ?? "Restaurant POS",
                      website: settings?.pos_receipt_footer || undefined,
                      phone: branch?.phone,
                      logo_url: settings?.receipt_show_logo ? settings.receipt_logo_url : undefined
                    }}
                    branch={{
                      name: branch?.name ?? "สาขาตัวอย่าง",
                      phone: branch?.phone
                    }}
                    cashier="พนักงานตัวอย่าง"
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="replacement">
          <Card>
            <CardContent className="space-y-6 p-5">
              <div className="space-y-2">
                <h3 className="text-lg font-semibold text-gray-900">กฎสินค้าทดแทนส่วนกลางของสาขา</h3>
                <p className="text-sm text-gray-500">
                  ใช้กำหนดว่าสินค้าใดควรถูกแนะนำเป็นตัวแทนหลักเวลา POS ทำรายการแลกสินค้าในสาขานี้
                </p>
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                <div className="space-y-3 rounded-2xl border border-slate-200 p-4">
                  <Label>ค้นหาสินค้าต้นทาง</Label>
                  <Input
                    placeholder="พิมพ์ชื่อ / SKU สินค้าที่ลูกค้าคืนบ่อย"
                    value={sourceSearch}
                    onChange={(event) => setSourceSearch(event.target.value)}
                  />
                  {selectedSourceProduct ? (
                    <div className="rounded-xl bg-blue-50 px-3 py-2 text-sm text-blue-800">
                      เลือกแล้ว: {selectedSourceProduct.name}
                    </div>
                  ) : null}
                  <div className="max-h-64 space-y-2 overflow-y-auto">
                    {(sourceProductsQuery.data ?? []).map((product) => (
                      <button
                        key={`source-${product.id}`}
                        type="button"
                        className={`w-full rounded-xl border px-3 py-3 text-left text-sm ${selectedSourceProduct?.id === product.id ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-white"}`}
                        onClick={() => setSelectedSourceProduct(product)}
                      >
                        <div className="font-medium text-slate-900">{product.name}</div>
                        <div className="text-xs text-slate-500">{product.sku}</div>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-3 rounded-2xl border border-slate-200 p-4">
                  <Label>ค้นหาสินค้าทดแทน</Label>
                  <Input
                    placeholder="พิมพ์ชื่อ / SKU สินค้าที่อยากให้ POS แนะนำแทน"
                    value={replacementSearch}
                    onChange={(event) => setReplacementSearch(event.target.value)}
                  />
                  {selectedReplacementProduct ? (
                    <div className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                      เลือกแล้ว: {selectedReplacementProduct.name}
                    </div>
                  ) : null}
                  <div className="max-h-64 space-y-2 overflow-y-auto">
                    {(replacementProductsQuery.data ?? []).map((product) => (
                      <button
                        key={`replacement-${product.id}`}
                        type="button"
                        className={`w-full rounded-xl border px-3 py-3 text-left text-sm ${selectedReplacementProduct?.id === product.id ? "border-emerald-500 bg-emerald-50" : "border-slate-200 bg-white"}`}
                        onClick={() => setSelectedReplacementProduct(product)}
                      >
                        <div className="font-medium text-slate-900">{product.name}</div>
                        <div className="text-xs text-slate-500">{product.sku}</div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-4">
                <div className="text-sm text-slate-600">
                  {selectedSourceProduct && selectedReplacementProduct
                    ? `${selectedSourceProduct.name} -> ${selectedReplacementProduct.name}`
                    : "เลือกสินค้าต้นทางและสินค้าทดแทนก่อนบันทึก"}
                </div>
                <Button
                  onClick={() => saveReplacementRuleMutation.mutate()}
                  disabled={!canEdit || !selectedSourceProduct || !selectedReplacementProduct || saveReplacementRuleMutation.isPending}
                >
                  บันทึกกฎส่วนกลาง
                </Button>
              </div>

              <div className="space-y-3">
                <div className="text-sm font-medium text-slate-700">กฎที่มีอยู่ในสาขานี้</div>
                {(replacementRulesQuery.data ?? []).length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
                    ยังไม่มีกฎสินค้าทดแทนส่วนกลาง
                  </div>
                ) : (
                  <div className="space-y-3">
                    {(replacementRulesQuery.data ?? []).map((rule) => (
                      <div key={rule.id} className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-4 md:flex-row md:items-center md:justify-between">
                        <div>
                          <div className="text-xs uppercase tracking-[0.25em] text-slate-500">Source to Replacement</div>
                          <div className="mt-1 font-medium text-slate-900">{rule.source_product_name} {"->"} {rule.replacement_product_name}</div>
                          <div className="mt-1 text-xs text-slate-500">สร้างเมื่อ {new Date(rule.created_at).toLocaleString("th-TH")}</div>
                        </div>
                        <Button
                          variant="outline"
                          className="border-red-200 text-red-700"
                          onClick={() => deleteReplacementRuleMutation.mutate(rule.source_product_id)}
                          disabled={!canEdit || deleteReplacementRuleMutation.isPending}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          ลบกฎ
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Field({
  label,
  children
}: {
  label: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <div className="grid gap-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function ToggleField({
  label,
  checked,
  onChange,
  warning,
  danger
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  warning?: string;
  danger?: boolean;
}): JSX.Element {
  return (
    <div className={`rounded-xl border px-4 py-3 ${danger ? "border-red-200 bg-red-50" : "border-gray-200"}`}>
      <label className="flex items-center gap-3 text-sm font-medium text-gray-900">
        <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
        {label}
      </label>
      {warning ? <p className="mt-2 text-sm text-red-700">{warning}</p> : null}
    </div>
  );
}
