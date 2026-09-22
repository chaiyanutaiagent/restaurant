import { useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Camera,
  ChefHat,
  ClipboardList,
  CloudUpload,
  LayoutGrid,
  LayoutList,
  Loader2,
  MonitorCog,
  Printer,
  Search,
  ShoppingBag,
  ShoppingCart,
  TabletSmartphone,
  UserRoundCheck,
  WifiOff,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useReactToPrint } from "react-to-print";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { useConfirm } from "@/hooks/useConfirm";
import { useLogout } from "@/hooks/useAuth";
import { authApi } from "@/lib/api";
import { branchApi } from "@/lib/adminApi";
import { crmApi } from "@/lib/crmApi";
import {
  buildCartItem,
  calcCart,
  calcChange,
  formatThaiDate,
  formatThaiCurrency,
  generateClientOrderId,
} from "@/lib/cartUtils";
import { db } from "@/lib/db";
import { posApi } from "@/lib/posApi";
import { productApi } from "@/lib/productApi";
import {
  getQueuedRestaurantOrder,
  getRestaurantOutboxSummary,
  loadRestaurantMenu,
  markRestaurantLocalSlip,
  queueRestaurantOrder,
  syncRestaurantPendingOrders,
  type RestaurantOutboxSummary,
} from "@/lib/restaurantOffline";
import { POS_CATALOG_ISOLATION_KEY, syncPendingSales, syncProductCatalog, syncStockBalances, useOfflineProducts, useOnlineStatus } from "@/lib/syncService";
import { wapApi, type WapOrder } from "@/lib/wapApi";
import { useAuthStore } from "@/stores/auth.store";
import { useDeviceStore } from "@/stores/device.store";
import type { BranchReplacementRule, BranchSettings } from "@/types/admin";
import type { ProductListItem, RetailLookupProduct, RetailLookupVariant } from "@/types/product";
import type { Customer, CustomerSearchResult, LoyaltySettings } from "@/types/crm";
import type { CartItem, CashierShift, ExchangeContextDraft, HeldSaleDraft, HoldDraftClaimResult, PaymentDraft, PaymentMethod, PendingSale, PricingCalculation, ReplacementRuleDraft, SaleOrder, ServerHoldDraft } from "@/types/pos";
import type { StockBalance, StockLocation } from "@/types/stock";
import CreateCustomerDialog from "@/pages/crm/CreateCustomerDialog";
import RedeemPointsDialog from "@/pages/crm/RedeemPointsDialog";
import CloseShiftDialog from "@/pages/pos/CloseShiftDialog";
import ReceiptView from "@/pages/pos/ReceiptView";
import ManagerApprovalDialog from "@/components/approval/ManagerApprovalDialog";
import BillReceiptCenterDialog from "@/components/pos/BillReceiptCenterDialog";
import DiscountWorkspaceDialog from "@/components/pos/DiscountWorkspaceDialog";
import HoldDraftWorkspaceDialog from "@/components/pos/HoldDraftWorkspaceDialog";
import PosWorkspaceNav from "@/components/pos/PosWorkspaceNav";
import RefundWorkspaceDialog from "@/components/pos/RefundWorkspaceDialog";
import TakeawayOrderSlip from "@/components/pos/TakeawayOrderSlip";
import type { ApprovalAction } from "@/types/approval";
import { PLATFORM_BRAND } from "@/config/platformBrand";

const SHIFT_CACHE_KEY = "restaurant-pos-current-shift";
const BARCODE_FORMATS = ["ean_13", "ean_8", "code_128", "code_39", "upc_a", "upc_e", "qr_code"] as const;

type BranchOption = {
  branch_id: string;
  branch_name: string;
  role_name: string;
  is_default: boolean;
};

type BarcodeDetectorResult = {
  rawValue?: string;
};

type BarcodeDetectorInstance = {
  detect: (source: ImageBitmapSource | HTMLVideoElement | HTMLCanvasElement | OffscreenCanvas) => Promise<BarcodeDetectorResult[]>;
};

type BarcodeDetectorCtor = new (options?: { formats?: string[] }) => BarcodeDetectorInstance;

function buildOfflineOrder(
  pendingSale: PendingSale,
  branchId: string,
  userId: string,
): SaleOrder {
  const createdAt = new Date(pendingSale.created_at).toISOString();
  return {
    id: pendingSale.client_order_id,
    order_number: `OFF-${new Date(pendingSale.created_at).toISOString().slice(0, 19).replace(/[^0-9]/g, "").slice(0, 14)}`,
    status: "pending_sync",
    branch_id: branchId,
    location_id: pendingSale.location_id,
    shift_id: pendingSale.shift_id,
    user_id: userId,
    customer_name: pendingSale.customer_name,
    customer_phone: pendingSale.customer_phone ?? null,
    subtotal: pendingSale.items.reduce((sum, item) => sum + item.subtotal, 0),
    discount_amount: pendingSale.discount_amount,
    vat_amount: pendingSale.items.reduce((sum, item) => sum + item.vat_amount, 0),
    total_amount: pendingSale.total_amount,
    paid_amount: pendingSale.paid_amount,
    change_amount: pendingSale.change_amount,
    is_offline: true,
    note: pendingSale.note ?? null,
    refund_amount: 0,
    created_at: createdAt,
    items: pendingSale.items.map((item, index) => ({
      id: `${pendingSale.client_order_id}-${index}`,
      product_id: item.product_id,
      variant_id: item.variant_id,
      product_name: item.product_name,
      variant_name: item.variant_name,
      sku: item.sku,
      unit_code: item.unit_code,
      qty: item.qty,
      unit_price: item.unit_price,
      original_price: item.original_price,
      discount_amount: item.discount_amount,
      vat_type: item.vat_type,
      vat_rate: item.vat_rate,
      vat_amount: item.vat_amount,
      subtotal: item.subtotal,
      refunded_qty: 0,
      refunded_amount: 0,
    })),
    payments: (pendingSale.payments ?? [
      {
        payment_method: pendingSale.payment_method,
        amount: pendingSale.paid_amount,
        reference_no: null,
      },
    ]).map((payment, index) => ({
      id: `${pendingSale.client_order_id}-payment-${index}`,
      payment_method: payment.payment_method,
      amount: payment.amount,
      reference_no: payment.reference_no ?? null,
      paid_at: createdAt,
    })),
  };
}

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

function tokenizeSearchTerms(value: string): string[] {
  return value
    .toLowerCase()
    .split(/[\s/(),.-]+/)
    .map((item) => item.trim())
    .filter((item) => item.length >= 2);
}

function getErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string | { message?: string; code?: string } } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;
  }
  return error instanceof Error ? error.message : "ทำรายการไม่สำเร็จ";
}

function getHoldConflict(error: unknown): { message: string; currentVersion?: number; currentStatus?: string; claimedBy?: string } | null {
  if (!error || typeof error !== "object" || !("response" in error)) return null;
  const response = (error as { response?: { status?: number; data?: { detail?: Record<string, unknown> } } }).response;
  const detail = response?.data?.detail;
  if (response?.status !== 409 || !detail || detail.code !== "draft_conflict") return null;
  return {
    message: typeof detail.message === "string" ? detail.message : "บิลพักถูกเปลี่ยนจากอีกเครื่อง",
    currentVersion: typeof detail.current_version === "number" ? detail.current_version : undefined,
    currentStatus: typeof detail.current_status === "string" ? detail.current_status : undefined,
    claimedBy: typeof detail.claimed_by === "string" ? detail.claimed_by : undefined,
  };
}

function normalizeHeldCartItem(item: CartItem): CartItem {
  return {
    ...item,
    qty: Number(item.qty),
    unit_price: Number(item.unit_price),
    original_price: Number(item.original_price),
    discount_amount: Number(item.discount_amount),
    vat_rate: Number(item.vat_rate),
    subtotal: Number(item.subtotal),
    vat_amount: Number(item.vat_amount),
    price_override: item.price_override
      ? { ...item.price_override, requested_unit_price: Number(item.price_override.requested_unit_price) }
      : null,
  };
}

function normalizeServerHoldDraft(draft: ServerHoldDraft): HeldSaleDraft {
  return {
    id: draft.id,
    server_id: draft.id,
    draft_no: draft.draft_no,
    shift_id: draft.origin_shift_id,
    location_id: draft.location_id,
    branch_id: draft.branch_id,
    sales_channel: draft.source_type === "takeaway" ? "takeaway" : "walk_in",
    label: draft.label,
    items: (draft.content.items ?? []).map(normalizeHeldCartItem),
    order_discount: Number(draft.content.order_discount ?? 0),
    loyalty_discount: Number(draft.content.loyalty_discount_intent ?? 0),
    payment_method: "cash",
    paid_amount: 0,
    payment_reference: null,
    split_payment_enabled: false,
    customer_name: draft.customer_display ?? "",
    customer_phone: "",
    customer_tax_id: "",
    customer_search: "",
    selected_customer: null,
    note: draft.note ?? "",
    held_at: new Date(draft.created_at).getTime(),
    sync_state: "synced",
    status: draft.status,
    version: draft.version,
    expires_at: draft.expires_at,
    owner_user_id: draft.owner_user_id,
    owner_display: draft.owner_display,
    assignee_user_id: draft.assignee_user_id,
    assignee_display: draft.assignee_display,
    origin_device_id: draft.origin_device_id,
    origin_device_code: draft.origin_device_code,
    origin_shift_number: draft.origin_shift_number,
    location_name: draft.location_name,
    table_id: draft.table_id,
    queue_label: draft.queue_label,
    claim_id: draft.claim_id,
    claimed_by: draft.claimed_by,
    claim_expires_at: draft.claim_expires_at,
    last_revalidation: draft.last_revalidation,
    resumed_at: draft.resumed_at,
    expired_at: draft.expired_at,
    cancelled_at: draft.cancelled_at,
    converted_at: draft.converted_at,
    cancel_reason: draft.cancel_reason,
    server_backed: true,
  };
}

function holdDraftPayload(draft: HeldSaleDraft, idempotencyKey: string): Record<string, unknown> {
  return {
    shift_id: draft.shift_id,
    location_id: draft.location_id,
    label: draft.label,
    source_type: draft.sales_channel === "takeaway" ? "takeaway" : "walk_in",
    customer_id: draft.selected_customer?.id ?? null,
    customer_display: draft.customer_name || draft.selected_customer?.display_name || null,
    note: draft.note || null,
    items: draft.items.map((item) => ({
      product_id: item.product_id,
      variant_id: item.variant_id,
      qty: item.qty,
      discount_amount: item.discount_amount,
      discount_type: item.discount_type,
      expected_unit_price: item.original_price,
      ...(item.expected_price_version ? { expected_price_version: item.expected_price_version } : {}),
      ...(item.price_override ? { price_override: item.price_override } : {}),
      display_name: item.product_name,
      display_variant_name: item.variant_name,
      display_sku: item.sku,
      display_unit_code: item.unit_code,
    })),
    order_discount: draft.order_discount,
    loyalty_discount_intent: draft.loyalty_discount,
    currency: "THB",
    cart_version: 1,
    idempotency_key: idempotencyKey,
  };
}

type ReplacementPlanEntry = {
  source: NonNullable<ExchangeContextDraft["source_items"]>[number];
  candidate: ProductListItem | null;
  matchedSource: "central" | "local" | "suggested";
};

type PendingManagerApproval = {
  action: ApprovalAction;
  requestPayload: Record<string, unknown>;
  reason: string;
  description: string;
  onApproved: (approvalToken: string) => Promise<void>;
};

type RetailResolvedLine = {
  product: ProductListItem;
  variant: RetailLookupVariant | null;
  qty: number;
  availableQty: number;
  serverPrice: number;
  priceVersion: string;
};

type RetailExceptionState =
  | { kind: "not_found"; code: string; message: string }
  | { kind: "variant_required"; code: string; message: string }
  | { kind: "unavailable"; code: string; message: string }
  | { kind: "stock_limit"; code: string; message: string; availableQty: number }
  | { kind: "price_changed"; code: string; message: string; previousPrice: number; serverPrice: number }
  | { kind: "permission" | "error"; code: string; message: string };

function maskPhone(phone: string | null | undefined): string {
  const digits = (phone ?? "").replace(/\D/g, "");
  if (digits.length < 7) return phone ? "***" : "-";
  return `${digits.slice(0, 3)}-***-${digits.slice(-4)}`;
}

const paymentMethodLabels: Record<PaymentMethod, string> = {
  cash: "เงินสด",
  promptpay: "PromptPay",
  credit_card: "บัตรเครดิต",
  bank_transfer: "โอนเงิน",
  other: "อื่นๆ",
};

export default function POSPage(): JSX.Element {
  const navigate = useNavigate();
  const logout = useLogout("/login?next=/pos");
  const location = useLocation();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const isOnline = useOnlineStatus();
  const companyId = useAuthStore((state) => state.companyId);
  const brandId = useAuthStore((state) => state.brandId);
  const branchId = useAuthStore((state) => state.branchId);
  const businessType = useAuthStore((state) => state.businessType);
  const targetDatabase = useAuthStore((state) => state.targetDatabase);
  const user = useAuthStore((state) => state.user);
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const isRetailMode = businessType === "retail_pos";
  const isTakeawayMode = !isRetailMode && new URLSearchParams(location.search).get("channel") === "takeaway";
  const retailContextValid = !isRetailMode || Boolean(companyId && brandId && branchId && targetDatabase === "retail_pos");
  const catalogScope = isRetailMode ? "retail_sale" as const : "restaurant_menu" as const;
  const catalogIsolationKey = `${companyId ?? "missing-company"}:${brandId ?? "missing-brand"}:${branchId ?? "missing-branch"}:${businessType ?? "missing-type"}:${catalogScope}`;
  const pairedDevice = useDeviceStore((state) => state.device);
  const deviceSessionHydrated = useDeviceStore((state) => state.hydrated);
  const hydrateDeviceSession = useDeviceStore((state) => state.hydrate);
  const [search, setSearch] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [cartItems, setCartItems] = useState<CartItem[]>([]);
  const [orderDiscount, setOrderDiscount] = useState(0);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("cash");
  const [paidAmount, setPaidAmount] = useState(0);
  const [creditRef, setCreditRef] = useState("");
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [promptPayTarget, setPromptPayTarget] = useState("");
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scannerError, setScannerError] = useState("");
  const [currentShift, setCurrentShift] = useState<CashierShift | null>(() => {
    const raw = window.localStorage.getItem(SHIFT_CACHE_KEY);
    if (!raw) {
      return null;
    }
    try {
      const cached = JSON.parse(raw) as CashierShift;
      return cached.user_id === user?.id && cached.branch_id === branchId ? cached : null;
    } catch {
      window.localStorage.removeItem(SHIFT_CACHE_KEY);
      return null;
    }
  });
  const [shiftGateOpen, setShiftGateOpen] = useState(false);
  const [openingCash, setOpeningCash] = useState(0);
  const [selectedLocationId, setSelectedLocationId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerTaxId, setCustomerTaxId] = useState("");
  const [customerSearch, setCustomerSearch] = useState("");
  const [debouncedCustomerSearch, setDebouncedCustomerSearch] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [loyaltyDiscount, setLoyaltyDiscount] = useState(0);
  const [createCustomerOpen, setCreateCustomerOpen] = useState(false);
  const [redeemOpen, setRedeemOpen] = useState(false);
  const [note, setNote] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showReceipt, setShowReceipt] = useState(false);
  const [lastOrder, setLastOrder] = useState<SaleOrder | null>(null);
  const [takeawayOrder, setTakeawayOrder] = useState<WapOrder | null>(null);
  const [takeawayResultOpen, setTakeawayResultOpen] = useState(false);
  const [takeawayPrintBusy, setTakeawayPrintBusy] = useState<"customer" | "kitchen" | null>(null);
  const [takeawayPendingPrint, setTakeawayPendingPrint] = useState<"customer" | "kitchen" | null>(null);
  const [takeawayOutboxSummary, setTakeawayOutboxSummary] = useState<RestaurantOutboxSummary>({
    pending: 0, syncing: 0, acknowledged: 0, reconciled: 0,
    needsReview: 0, rejected: 0, quarantined: 0, unknown: 0,
  });
  const [closeShiftOpen, setCloseShiftOpen] = useState(false);
  const [confirm, ConfirmDialog] = useConfirm();
  const [heldBillsOpen, setHeldBillsOpen] = useState(false);
  const [holdCreateOpen, setHoldCreateOpen] = useState(false);
  const [customerSectionOpen, setCustomerSectionOpen] = useState(false);
  const [cardDensity, setCardDensity] = useState<"normal" | "compact" | "list">(() => {
    return (window.localStorage.getItem("pos-card-density") as "normal" | "compact" | "list") ?? "normal";
  });
  const [holdLabel, setHoldLabel] = useState("");
  const [heldBillsVersion, setHeldBillsVersion] = useState(0);
  const [heldBillsSearch, setHeldBillsSearch] = useState("");
  const [heldBillsFilter, setHeldBillsFilter] = useState<"active" | "mine" | "counter" | "history">("active");
  const [heldBillsBusy, setHeldBillsBusy] = useState<string | null>(null);
  const [pendingResumeDraft, setPendingResumeDraft] = useState<HeldSaleDraft | null>(null);
  const [pendingRevalidation, setPendingRevalidation] = useState<{ draft: HeldSaleDraft; claim: HoldDraftClaimResult } | null>(null);
  const [holdConflict, setHoldConflict] = useState<{ message: string; currentVersion?: number; currentStatus?: string; claimedBy?: string } | null>(null);
  const [resumedHoldDraft, setResumedHoldDraft] = useState<{ id: string; version: number } | null>(null);
  const [replacementRulesVersion, setReplacementRulesVersion] = useState(0);
  const [recentSalesOpen, setRecentSalesOpen] = useState(false);
  const [discountWorkspaceOpen, setDiscountWorkspaceOpen] = useState(false);
  const [priceEditorOpen, setPriceEditorOpen] = useState(false);
  const [priceEditProductId, setPriceEditProductId] = useState<string | null>(null);
  const [priceEditVariantId, setPriceEditVariantId] = useState<string | null>(null);
  const [priceEditValue, setPriceEditValue] = useState("");
  const [priceEditReason, setPriceEditReason] = useState("");
  const [priceEditReasonCode, setPriceEditReasonCode] = useState<"customer_recovery" | "price_match" | "manager_comp" | "damaged_item" | "manual_correction" | "other">("other");
  const [voidOrder, setVoidOrder] = useState<SaleOrder | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [refundWorkspaceOrder, setRefundWorkspaceOrder] = useState<SaleOrder | null>(null);
  const [pendingManagerApproval, setPendingManagerApproval] = useState<PendingManagerApproval | null>(null);
  const [exchangeContext, setExchangeContext] = useState<ExchangeContextDraft | null>(null);
  const [splitPaymentEnabled, setSplitPaymentEnabled] = useState(false);
  const [secondaryPaymentMethod, setSecondaryPaymentMethod] = useState<PaymentMethod>("promptpay");
  const [secondaryPaymentAmount, setSecondaryPaymentAmount] = useState(0);
  const [secondaryPaymentReference, setSecondaryPaymentReference] = useState("");
  const [deviceStatusOpen, setDeviceStatusOpen] = useState(false);
  const [retailException, setRetailException] = useState<RetailExceptionState | null>(null);
  const [retailLookupBusy, setRetailLookupBusy] = useState(false);
  const [retailVariantProduct, setRetailVariantProduct] = useState<RetailLookupProduct | null>(null);
  const [selectedRetailVariantId, setSelectedRetailVariantId] = useState<string | null>(null);
  const [pendingRetailLine, setPendingRetailLine] = useState<RetailResolvedLine | null>(null);
  const [pendingRetailQuote, setPendingRetailQuote] = useState<PricingCalculation | null>(null);
  const [lastSyncAt, setLastSyncAt] = useState<Date | null>(null);
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [autoPrintReceipt, setAutoPrintReceipt] = useState(() => window.localStorage.getItem("pos-auto-print-receipt") === "true");
  const searchRef = useRef<HTMLInputElement | null>(null);
  const cashInputRef = useRef<HTMLInputElement | null>(null);
  const receiptRef = useRef<HTMLDivElement | null>(null);
  const takeawayCustomerSlipRef = useRef<HTMLDivElement | null>(null);
  const takeawayKitchenSlipRef = useRef<HTMLDivElement | null>(null);
  const scannerVideoRef = useRef<HTMLVideoElement | null>(null);
  const checkoutIdRef = useRef(generateClientOrderId());
  const openShiftIdempotencyRef = useRef(`shift-open:${generateClientOrderId()}`);

  const scannerStreamRef = useRef<MediaStream | null>(null);
  const scannerFrameRef = useRef<number | null>(null);
  const autoPrintedOrderRef = useRef<string | null>(null);
  const offlineProducts = useOfflineProducts(searchTerm, catalogRevision);
  const handlePrint = useReactToPrint({ contentRef: receiptRef });
  const printTakeawayCustomerSlip = useReactToPrint({ contentRef: takeawayCustomerSlipRef });
  const printTakeawayKitchenSlip = useReactToPrint({ contentRef: takeawayKitchenSlipRef });

  const branchQuery = useQuery({
    queryKey: ["pos", "branches"],
    queryFn: async () => {
      const response = await authApi.myBranches();
      return response.data.data as BranchOption[];
    },
    enabled: Boolean(user),
  });

  useEffect(() => {
    if (!deviceSessionHydrated) void hydrateDeviceSession();
  }, [deviceSessionHydrated, hydrateDeviceSession]);

  const locationsQuery = useQuery({
    queryKey: ["pos", "locations", branchId],
    queryFn: async () => {
      const response = await posApi.listLocations(branchId ?? undefined);
      return response.data.data as StockLocation[];
    },
    enabled: Boolean(branchId),
  });

  const currentShiftQuery = useQuery({
    queryKey: ["pos", "current-shift", branchId],
    queryFn: async () => {
      const response = await posApi.getCurrentShift();
      return response.data.data as CashierShift | null;
    },
    enabled: Boolean(branchId) && isOnline,
  });
  const branchSettingsQuery = useQuery({
    queryKey: ["pos", "branch-settings", branchId],
    queryFn: async () => {
      if (!branchId) {
        return null;
      }
      return (await branchApi.getSettings(branchId)).data.data as BranchSettings;
    },
    enabled: Boolean(branchId) && isOnline,
  });

  const takeawayMenuQuery = useQuery({
    queryKey: ["pos", "takeaway-menu", branchId],
    queryFn: () => loadRestaurantMenu(),
    enabled: isTakeawayMode && Boolean(branchId),
    retry: false,
  });

  const onlineSearchQuery = useQuery({
    queryKey: ["pos", "products", catalogScope, catalogIsolationKey, searchTerm],
    queryFn: async () => {
      const response = await productApi.list({
        search: searchTerm,
        is_active: true,
        catalog_scope: catalogScope,
        page: 1,
        limit: 100,
      });
      return response.data.data as ProductListItem[];
    },
    enabled: isOnline && retailContextValid && searchTerm.trim().length > 0,
  });
  const loyaltySettingsQuery = useQuery({
    queryKey: ["pos", "loyalty-settings"],
    queryFn: async () => (await crmApi.getSettings()).data.data as LoyaltySettings,
    enabled: isOnline
  });
  const customerSearchQuery = useQuery({
    queryKey: ["pos", "customer-search", debouncedCustomerSearch],
    queryFn: async () => (await crmApi.searchCustomers(debouncedCustomerSearch, 10)).data.data as CustomerSearchResult[],
    enabled: debouncedCustomerSearch.trim().length >= 3
  });

  const categoriesQuery = useQuery({
    queryKey: ["pos", "categories"],
    queryFn: async () => {
      const rows = await db.categories.toArray();
      return rows;
    },
  });

  const stockBalancesQuery = useQuery({
    queryKey: ["pos", "stock-balances", branchId],
    queryFn: async () => {
      const rows = await db.stockBalances.toArray();
      return rows.filter((row) => !branchId || row.branch_id === branchId);
    },
  });
  const heldBillsQuery = useQuery({
    queryKey: ["pos", "held-bills", currentShift?.id, branchId, heldBillsVersion, isOnline, heldBillsSearch, heldBillsFilter],
    queryFn: async () => {
      if (!currentShift) {
        return [] as HeldSaleDraft[];
      }
      const localRows = await db.heldBills.where("shift_id").equals(currentShift.id).toArray();
      if (!isOnline || !hasPermission("pos.draft.view")) {
        return localRows.sort((left, right) => right.held_at - left.held_at);
      }
      if (hasPermission("pos.draft.create")) {
        for (const local of localRows.filter((row) => !row.server_backed)) {
          try {
            await posApi.createHoldDraft(holdDraftPayload(local, `offline-hold:${local.id}`));
            await db.heldBills.delete(local.id);
          } catch {
            await db.heldBills.update(local.id, { sync_state: "needs_review" });
          }
        }
      }
      const response = await posApi.listHoldDrafts({
        mine: heldBillsFilter === "mine",
        this_counter: heldBillsFilter === "counter",
        include_history: heldBillsFilter === "history",
        search: heldBillsSearch.trim() || undefined,
      });
      const serverRows = response.data.data.map(normalizeServerHoldDraft);
      const remainingLocal = await db.heldBills.where("shift_id").equals(currentShift.id).toArray();
      return [...serverRows, ...remainingLocal].sort((left, right) => right.held_at - left.held_at);
    },
    enabled: Boolean(currentShift),
    refetchInterval: heldBillsOpen && isOnline ? 15_000 : false,
  });
  const replacementRulesQuery = useQuery({
    queryKey: ["pos", "local-replacement-rules", branchId, replacementRulesVersion],
    queryFn: async () => {
      const rows = await db.replacementRules.toArray();
      return rows.filter((row) => row.branch_id === null || row.branch_id === branchId);
    },
    enabled: Boolean(branchId),
  });
  const centralReplacementRulesQuery = useQuery({
    queryKey: ["pos", "central-replacement-rules", branchId],
    queryFn: async () => {
      if (!branchId) {
        return [] as BranchReplacementRule[];
      }
      const response = await branchApi.listReplacementRules(branchId);
      return response.data.data as BranchReplacementRule[];
    },
    enabled: Boolean(branchId) && isOnline,
  });
  const recentSalesQuery = useQuery({
    queryKey: ["pos", "recent-sales", currentShift?.id],
    queryFn: async () => {
      if (!currentShift) {
        return [] as SaleOrder[];
      }
      const response = await posApi.listSales({ shift_id: currentShift.id, limit: 100, page: 1 });
      return response.data.data as SaleOrder[];
    },
    enabled: Boolean(currentShift) && isOnline,
  });

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearchTerm(search);
    }, 200);
    return () => window.clearTimeout(timeout);
  }, [search]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedCustomerSearch(customerSearch);
    }, 400);
    return () => window.clearTimeout(timeout);
  }, [customerSearch]);

  useEffect(() => {
    if (currentShift && (currentShift.user_id !== user?.id || currentShift.branch_id !== branchId)) {
      setCurrentShift(null);
      window.localStorage.removeItem(SHIFT_CACHE_KEY);
    }
  }, [branchId, currentShift, user?.id]);

  useEffect(() => {
    if (currentShiftQuery.data !== undefined) {
      setCurrentShift(currentShiftQuery.data);
      if (currentShiftQuery.data) {
        window.localStorage.setItem(SHIFT_CACHE_KEY, JSON.stringify(currentShiftQuery.data));
      } else {
        window.localStorage.removeItem(SHIFT_CACHE_KEY);
      }
      setShiftGateOpen(!currentShiftQuery.data);
    }
  }, [currentShiftQuery.data]);

  useEffect(() => {
    let active = true;
    if (!isOnline || !retailContextValid) return () => { active = false; };
    void Promise.all([
      syncProductCatalog(catalogScope, catalogIsolationKey),
      syncStockBalances(branchId ?? undefined),
      companyId && branchId && user && (businessType === "restaurant" || businessType === "retail_pos")
        ? syncPendingSales({ companyId, branchId, userId: user.id, businessType })
        : Promise.resolve({ synced: 0, failed: 0 }),
    ]).then(() => {
      if (!active) return;
      setCatalogRevision((current) => current + 1);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["pos", "categories"] }),
        queryClient.invalidateQueries({ queryKey: ["pos", "stock-balances"] }),
      ]);
      setLastSyncAt(new Date());
    }).catch(() => undefined);
    return () => { active = false; };
  }, [branchId, businessType, catalogIsolationKey, catalogScope, companyId, isOnline, queryClient, retailContextValid, user]);

  useEffect(() => {
    if (!isTakeawayMode) return;
    let active = true;
    void (async () => {
      const summary = isOnline
        ? await syncRestaurantPendingOrders().catch(() => getRestaurantOutboxSummary())
        : await getRestaurantOutboxSummary();
      if (!active) return;
      setTakeawayOutboxSummary(summary);
      if (isOnline) {
        await takeawayMenuQuery.refetch();
        if (takeawayOrder?.client_order_id) {
          const resolved = await getQueuedRestaurantOrder(takeawayOrder.client_order_id);
          if (active && resolved) setTakeawayOrder(resolved);
        }
      }
    })();
    return () => {
      active = false;
    };
    // Reconnect or entering Takeaway mode is the trigger; order/query updates must not loop the sync.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOnline, isTakeawayMode]);

  useEffect(() => {
    if (!showReceipt || !lastOrder || !autoPrintReceipt || autoPrintedOrderRef.current === lastOrder.id) {
      return;
    }
    autoPrintedOrderRef.current = lastOrder.id;
    const timeout = window.setTimeout(() => {
      void handlePrint();
    }, 350);
    return () => window.clearTimeout(timeout);
  }, [autoPrintReceipt, handlePrint, lastOrder, showReceipt]);

  useEffect(() => {
    if (!takeawayPendingPrint || !takeawayOrder) return;
    const timeout = window.setTimeout(() => {
      if (takeawayPendingPrint === "customer") {
        void printTakeawayCustomerSlip();
      } else {
        void printTakeawayKitchenSlip();
      }
      setTakeawayPendingPrint(null);
    }, 150);
    return () => window.clearTimeout(timeout);
  }, [printTakeawayCustomerSlip, printTakeawayKitchenSlip, takeawayOrder, takeawayPendingPrint]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "F1" || event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "F2") {
        event.preventDefault();
        cashInputRef.current?.focus();
      }
      if (event.key === "Escape") {
        setSearch("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const branches = branchQuery.data ?? [];
  const branchName = branches.find((item) => item.branch_id === branchId)?.branch_name ?? "สาขาหลัก";
  const locations = locationsQuery.data ?? [];
  const catalogCategories = categoriesQuery.data ?? [];
  const stockBalances = stockBalancesQuery.data ?? [];
  const catalogCacheTrusted = window.localStorage.getItem(POS_CATALOG_ISOLATION_KEY) === catalogIsolationKey;
  const baseProducts = (isOnline && searchTerm.trim().length > 0
    ? onlineSearchQuery.data
    : catalogCacheTrusted ? offlineProducts : []) ?? [];
  const takeawayMenuByProductId = useMemo(
    () => new Map((takeawayMenuQuery.data?.products ?? []).map((product) => [product.id, product])),
    [takeawayMenuQuery.data?.products],
  );
  const restaurantProducts = useMemo(
    () => baseProducts.filter((product) => product.product_type === "menu_item" && product.is_for_sale),
    [baseProducts],
  );
  const retailProducts = useMemo(
    () => baseProducts.filter((product) => !["menu_item", "raw_material"].includes(product.product_type) && product.is_for_sale),
    [baseProducts],
  );
  const eligibleProducts = isRetailMode ? retailProducts : restaurantProducts;
  const products = useMemo(() => {
    if (!isTakeawayMode) return eligibleProducts;
    if (!takeawayMenuQuery.data) return [];
    return restaurantProducts
      .filter((product) => takeawayMenuByProductId.get(product.id)?.is_available)
      .map((product) => ({
        ...product,
        selling_price: Number(takeawayMenuByProductId.get(product.id)?.selling_price ?? product.selling_price),
      }));
  }, [eligibleProducts, isTakeawayMode, restaurantProducts, takeawayMenuByProductId, takeawayMenuQuery.data]);
  const categories = useMemo(() => {
    const categoryById = new Map(catalogCategories.map((category) => [category.id, category]));
    const groups = new Map<string, { key: string; name: string; ids: Set<string> }>();
    for (const product of eligibleProducts) {
      if (!product.category_id) continue;
      const category = categoryById.get(product.category_id);
      if (!category?.is_active) continue;
      const key = category.name.trim().replace(/\s+/g, " ").toLocaleLowerCase("th-TH");
      const group = groups.get(key) ?? { key, name: category.name.trim(), ids: new Set<string>() };
      group.ids.add(category.id);
      groups.set(key, group);
    }
    return [...groups.values()].sort((left, right) => left.name.localeCompare(right.name, "th"));
  }, [catalogCategories, eligibleProducts]);
  const stockByProduct = useMemo(
    () => new Map(stockBalances.map((item) => [`${item.product_id}:${item.variant_id ?? "base"}`, item])),
    [stockBalances],
  );

  const visibleProducts = useMemo(() => {
    return products.filter((item) => {
      const category = categories.find((entry) => entry.key === selectedCategory);
      if (category && (!item.category_id || !category.ids.has(item.category_id))) {
        return false;
      }
      return true;
    });
  }, [categories, products, selectedCategory]);

  const cart = useMemo(() => calcCart(cartItems, orderDiscount, "amount"), [cartItems, orderDiscount]);
  const takeawayExpectedTotal = useMemo(
    () => roundMoney(cart.items.reduce((sum, item) => {
      const menuProduct = takeawayMenuByProductId.get(item.product_id);
      return sum + Number(menuProduct?.selling_price ?? item.unit_price) * Number(item.qty);
    }, 0)),
    [cart.items, takeawayMenuByProductId],
  );
  const exchangeCreditAvailable = exchangeContext?.refund_amount ?? 0;
  const exchangeCreditApplied = useMemo(
    () => roundMoney(Math.min(exchangeCreditAvailable, Math.max(cart.total_amount - loyaltyDiscount, 0))),
    [cart.total_amount, exchangeCreditAvailable, loyaltyDiscount],
  );
  const exchangeCreditRemaining = useMemo(
    () => roundMoney(Math.max(exchangeCreditAvailable - exchangeCreditApplied, 0)),
    [exchangeCreditApplied, exchangeCreditAvailable],
  );
  const totalDiscount = orderDiscount + loyaltyDiscount + exchangeCreditApplied;
  useEffect(() => {
    checkoutIdRef.current = generateClientOrderId();
  }, [cartItems, orderDiscount, loyaltyDiscount, exchangeCreditApplied, selectedCustomer?.id]);
  const standardFinalTotal = Math.max(cart.total_amount - loyaltyDiscount - exchangeCreditApplied, 0);
  const finalTotal = isTakeawayMode ? takeawayExpectedTotal : standardFinalTotal;
  const secondaryAmount = Math.max(0, Math.min(secondaryPaymentAmount, finalTotal));
  const primaryDueAmount = Math.max(finalTotal - (splitPaymentEnabled ? secondaryAmount : 0), 0);
  const currentPaidAmount = useMemo(() => {
    if (splitPaymentEnabled) {
      if (paymentMethod === "cash") {
        return Math.max(paidAmount, 0) + secondaryAmount;
      }
      return finalTotal;
    }
    return paymentMethod === "cash" ? paidAmount : finalTotal;
  }, [finalTotal, paidAmount, paymentMethod, secondaryAmount, splitPaymentEnabled]);
  const changeAmount = calcChange(finalTotal, currentPaidAmount);
  const paymentReference = useMemo(() => {
    if (paymentMethod === "credit_card" || paymentMethod === "bank_transfer") {
      return creditRef.trim() || null;
    }
    return null;
  }, [creditRef, paymentMethod]);
  const checkoutPayments = useMemo((): PaymentDraft[] => {
    if (splitPaymentEnabled) {
      const rows: PaymentDraft[] = [];
      const primaryAmount = paymentMethod === "cash" ? Math.max(paidAmount, 0) : primaryDueAmount;
      if (primaryAmount > 0) {
        rows.push({
          payment_method: paymentMethod,
          amount: primaryAmount,
          reference_no: paymentReference,
        });
      }
      if (secondaryAmount > 0) {
        rows.push({
          payment_method: secondaryPaymentMethod,
          amount: secondaryAmount,
          reference_no:
            secondaryPaymentMethod === "credit_card" || secondaryPaymentMethod === "bank_transfer"
              ? secondaryPaymentReference.trim() || null
              : null,
        });
      }
      return rows;
    }
    return [
      {
        payment_method: paymentMethod,
        amount: paymentMethod === "cash" ? Math.max(paidAmount, 0) : finalTotal,
        reference_no: paymentReference,
      },
    ];
  }, [
    finalTotal,
    paidAmount,
    paymentMethod,
    paymentReference,
    primaryDueAmount,
    secondaryAmount,
    secondaryPaymentMethod,
    secondaryPaymentReference,
    splitPaymentEnabled,
  ]);
  const promptPayAmount = splitPaymentEnabled ? primaryDueAmount : finalTotal;
  const vatIncludedAmount = useMemo(
    () => cart.items.filter((item) => item.vat_type === "included").reduce((sum, item) => sum + item.vat_amount, 0),
    [cart.items],
  );
  const vatExcludedAmount = useMemo(
    () => cart.items.filter((item) => item.vat_type === "excluded").reduce((sum, item) => sum + item.vat_amount, 0),
    [cart.items],
  );
  const vatExemptSubtotal = useMemo(
    () => cart.items.filter((item) => item.vat_type === "exempt").reduce((sum, item) => sum + item.subtotal, 0),
    [cart.items],
  );
  const cameraSupported = typeof window !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);

  useEffect(() => {
    const settings = branchSettingsQuery.data;
    if (!settings) {
      return;
    }
    if (!settings.pos_allow_discount && orderDiscount !== 0) {
      setOrderDiscount(0);
      return;
    }
    const maxDiscountAmount = (cart.subtotal * settings.pos_max_discount_pct) / 100;
    if (orderDiscount > maxDiscountAmount) {
      setOrderDiscount(maxDiscountAmount);
    }
  }, [branchSettingsQuery.data, cart.subtotal, orderDiscount]);

  useEffect(() => {
    if (!isTakeawayMode) return;
    setOrderDiscount(0);
    setLoyaltyDiscount(0);
    setExchangeContext(null);
  }, [isTakeawayMode]);

  useEffect(() => {
    if (!isRetailMode) return;
    // Retail provider and loyalty reservations remain fail-closed until their
    // Server contracts are available. Cash uses the existing idempotent Sale path.
    setLoyaltyDiscount(0);
    setPaymentMethod("cash");
    setSplitPaymentEnabled(false);
    setSecondaryPaymentAmount(0);
    setSecondaryPaymentReference("");
  }, [isRetailMode]);

  useEffect(() => {
    if (paymentMethod === "promptpay" && promptPayAmount > 0) {
      void posApi.getPromptPayQR(promptPayAmount)
        .then(async (response) => {
          const payload = response.data.data.payload as string;
          const dataUrl = await QRCode.toDataURL(payload, { width: 200, margin: 1 });
          setQrDataUrl(dataUrl);
          setPromptPayTarget((response.data.data.target as string | undefined) ?? "");
        })
        .catch(() => {
          setQrDataUrl("");
          setPromptPayTarget("");
        });
    }
  }, [paymentMethod, promptPayAmount]);

  useEffect(() => {
    let cancelled = false;
    let fallbackControls: { stop: () => void } | null = null;
    let codeHandled = false;

    const stopScanner = () => {
      if (scannerFrameRef.current !== null) {
        window.cancelAnimationFrame(scannerFrameRef.current);
        scannerFrameRef.current = null;
      }
      if (scannerStreamRef.current) {
        scannerStreamRef.current.getTracks().forEach((track) => track.stop());
        scannerStreamRef.current = null;
      }
      fallbackControls?.stop();
      fallbackControls = null;
    };

    if (!scannerOpen) {
      stopScanner();
      return;
    }

    setScannerError("");

    if (!cameraSupported) {
      setScannerError("อุปกรณ์นี้ยังไม่รองรับการสแกนด้วยกล้อง");
      return;
    }

    const handleDetectedCode = (rawCode: string, stop: () => void) => {
      const code = rawCode.trim();
      if (!code || cancelled || codeHandled) {
        return;
      }
      codeHandled = true;
      stop();
      setScannerOpen(false);
      void handleProductCodeLookup(code);
    };

    const startNativeScanner = (BarcodeDetectorClass: BarcodeDetectorCtor) => {
      let detector: BarcodeDetectorInstance;
      try {
        detector = new BarcodeDetectorClass({ formats: [...BARCODE_FORMATS] });
      } catch {
        void startFallbackScanner();
        return;
      }

      const scanLoop = async () => {
        if (cancelled) {
          return;
        }
        const video = scannerVideoRef.current;
        if (video && video.readyState >= HTMLMediaElement.HAVE_ENOUGH_DATA) {
          try {
            const results = await detector.detect(video);
            const code = results.find((item) => item.rawValue?.trim())?.rawValue;
            if (code) {
              handleDetectedCode(code, stopScanner);
              return;
            }
          } catch {
            setScannerError("กล้องเปิดได้ แต่ยังอ่านบาร์โค้ดไม่ได้");
          }
        }
        scannerFrameRef.current = window.requestAnimationFrame(() => {
          void scanLoop();
        });
      };

      void navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } } })
        .then(async (stream) => {
          if (cancelled) {
            stream.getTracks().forEach((track) => track.stop());
            return;
          }
          scannerStreamRef.current = stream;
          setScannerError("");
          if (scannerVideoRef.current) {
            scannerVideoRef.current.srcObject = stream;
            await scannerVideoRef.current.play();
          }
          await scanLoop();
        })
        .catch(() => {
          if (!cancelled) {
            setScannerError("ไม่สามารถเปิดกล้องเพื่อสแกนบาร์โค้ดได้ กรุณาอนุญาตสิทธิ์กล้อง");
          }
        });
    };

    async function startFallbackScanner() {
      try {
        const { BarcodeFormat, BrowserMultiFormatReader } = await import("@zxing/browser");
        if (cancelled) {
          return;
        }
        const video = scannerVideoRef.current;
        if (!video) {
          return;
        }

        const reader = new BrowserMultiFormatReader();
        reader.possibleFormats = [
          BarcodeFormat.EAN_13,
          BarcodeFormat.EAN_8,
          BarcodeFormat.CODE_128,
          BarcodeFormat.CODE_39,
          BarcodeFormat.UPC_A,
          BarcodeFormat.UPC_E,
          BarcodeFormat.QR_CODE,
        ];
        fallbackControls = await reader.decodeFromConstraints(
          { audio: false, video: { facingMode: { ideal: "environment" } } },
          video,
          (result, _error, controls) => {
            const code = result?.getText();
            if (code) {
              handleDetectedCode(code, () => controls.stop());
            }
          },
        );
      } catch {
        if (!cancelled) {
          setScannerError("ไม่สามารถเปิดกล้องเพื่อสแกนบาร์โค้ดได้ กรุณาอนุญาตสิทธิ์กล้อง");
        }
      }
    }

    const BarcodeDetectorClass = (window as Window & { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector;
    if (BarcodeDetectorClass) {
      startNativeScanner(BarcodeDetectorClass);
    } else {
      void startFallbackScanner();
    }

    return () => {
      cancelled = true;
      stopScanner();
    };
  }, [cameraSupported, scannerOpen]);

  function updateCartItem(
    productId: string,
    updater: (item: CartItem) => CartItem | null,
    variantId: string | null = null,
  ): void {
    setCartItems((current) =>
      current
        .map((item) => (item.product_id === productId && item.variant_id === variantId ? updater(item) : item))
        .filter((item): item is CartItem => item !== null)
    );
  }

  function getAvailableStock(productId: string, variantId: string | null = null): number {
    const row = stockByProduct.get(`${productId}:${variantId ?? "base"}`);
    return Number(row?.qty_available ?? 0);
  }

  function addToCart(product: ProductListItem, qty = 1): void {
    if (isRetailMode && (!retailContextValid || !catalogCacheTrusted || ["menu_item", "raw_material"].includes(product.product_type))) {
      toast({
        title: "เพิ่มสินค้าไม่ได้",
        description: "Catalog หรือ signed Retail context ไม่ตรงกับ Counter นี้",
        variant: "destructive",
      });
      return;
    }
    const available = getAvailableStock(product.id, null);
    if (available <= 0) {
      if (isRetailMode) {
        setRetailException({
          kind: "unavailable",
          code: product.sku,
          message: `${product.name} ไม่มี Stock ที่ขายได้ในคลังของกะนี้`,
        });
      }
      return;
    }
    setCartItems((current) => {
      const existing = current.find((item) => item.product_id === product.id && item.variant_id === null);
      const safeQty = Math.max(1, Math.floor(qty));
      if (existing) {
        if (existing.qty >= available) {
          if (isRetailMode) {
            setRetailException({
              kind: "stock_limit",
              code: product.sku,
              message: `${product.name} ขายได้สูงสุด ${available} ชิ้น`,
              availableQty: available,
            });
          }
          return current;
        }
        const nextQty = Math.min(existing.qty + safeQty, available);
        return current.map((item) =>
          item.product_id === product.id && item.variant_id === null
            ? { ...item, qty: nextQty, subtotal: nextQty * item.unit_price, vat_amount: item.vat_amount }
            : item
        );
      }
      return [...current, buildCartItem(product, Math.min(safeQty, available))];
    });
  }

  function addRetailResolvedLine(line: RetailResolvedLine): void {
    const variantId = line.variant?.id ?? null;
    const safeQty = Math.max(1, Math.floor(line.qty));
    setCartItems((current) => {
      const existing = current.find(
        (item) => item.product_id === line.product.id && item.variant_id === variantId,
      );
      const currentQty = existing?.qty ?? 0;
      const nextQty = currentQty + safeQty;
      if (nextQty > line.availableQty) {
        setRetailException({
          kind: "stock_limit",
          code: line.variant?.sku ?? line.product.sku,
          message: `${line.product.name} ขายได้สูงสุด ${line.availableQty} ชิ้น`,
          availableQty: line.availableQty,
        });
        return current;
      }
      if (existing) {
        return current.map((item) => item.product_id === line.product.id && item.variant_id === variantId
          ? {
              ...item,
              qty: nextQty,
              unit_price: line.serverPrice,
              original_price: line.serverPrice,
              expected_price_version: line.priceVersion,
              subtotal: nextQty * line.serverPrice,
            }
          : item);
      }
      const item = buildCartItem(line.product, safeQty, line.serverPrice);
      return [...current, {
        ...item,
        variant_id: variantId,
        variant_name: line.variant?.name ?? null,
        sku: line.variant?.sku ?? line.product.sku,
        unit_code: line.product.unit?.code ?? null,
        expected_price_version: line.priceVersion,
      }];
    });
    setRetailException(null);
    setPendingRetailLine(null);
    setPendingRetailQuote(null);
    setSearch("");
    window.setTimeout(() => searchRef.current?.focus(), 0);
  }

  function updateCartQuantity(item: CartItem, requestedQty: number): void {
    const available = getAvailableStock(item.product_id, item.variant_id);
    const safeQty = Math.max(0, Math.floor(Number.isFinite(requestedQty) ? requestedQty : 1));
    if (safeQty > available) {
      if (isRetailMode) {
        setRetailException({
          kind: "stock_limit",
          code: item.sku,
          message: `${item.product_name} ขายได้สูงสุด ${available} ชิ้น`,
          availableQty: available,
        });
      }
      return;
    }
    updateCartItem(
      item.product_id,
      (current) => safeQty <= 0 ? null : { ...current, qty: safeQty, subtotal: safeQty * current.unit_price },
      item.variant_id,
    );
    setRetailException(null);
  }

  async function validateRetailLine(
    lookup: RetailLookupProduct,
    sourceProduct: ProductListItem,
    variant: RetailLookupVariant | null,
    qty = 1,
  ): Promise<void> {
    const serverLookupPrice = Number(variant?.server_price ?? lookup.server_price);
    const expectedPrice = Number(variant?.server_price ?? sourceProduct.selling_price);
    const quote = (await posApi.calculatePricing({
      items: [{
        product_id: lookup.id,
        variant_id: variant?.id ?? lookup.selected_variant_id,
        qty,
        discount_amount: 0,
        discount_type: "amount",
        expected_unit_price: expectedPrice,
      }],
      discount_amount: 0,
      discount_type: "amount",
      channel: "pos",
      currency: "THB",
      idempotency_key: `retail-add:${checkoutIdRef.current}:${lookup.id}:${variant?.id ?? lookup.selected_variant_id ?? "base"}`,
      cart_version: Math.max(1, cartItems.length + 1),
    })).data.data;
    const pricedLine = quote.lines[0];
    if (!pricedLine) {
      throw new Error("Server ไม่ส่งผลตรวจราคาสินค้า")
    }
    const selectedVariant = variant ?? lookup.variants.find((item) => item.id === lookup.selected_variant_id) ?? null;
    const resolved: RetailResolvedLine = {
      product: sourceProduct,
      variant: selectedVariant,
      qty,
      availableQty: Number(selectedVariant?.available_qty ?? lookup.available_qty),
      serverPrice: Number(pricedLine.authoritative_unit_price),
      priceVersion: pricedLine.price_version,
    };
    const cachedPrice = Number(sourceProduct.selling_price);
    if (
      pricedLine.discrepancy
      || Math.abs(Number(pricedLine.authoritative_unit_price) - serverLookupPrice) >= 0.01
      || (!selectedVariant && Math.abs(Number(pricedLine.authoritative_unit_price) - cachedPrice) >= 0.01)
    ) {
      setPendingRetailLine(resolved);
      setRetailException({
        kind: "price_changed",
        code: selectedVariant?.sku ?? sourceProduct.sku,
        message: `ราคา ${sourceProduct.name} เปลี่ยนหลัง Server ตรวจสอบ`,
        previousPrice: selectedVariant ? serverLookupPrice : cachedPrice,
        serverPrice: resolved.serverPrice,
      });
      return;
    }
    addRetailResolvedLine(resolved);
  }

  async function handleRetailLookup(code: string, source?: ProductListItem, qty = 1): Promise<void> {
    if (!currentShift?.location_id) {
      setRetailException({ kind: "permission", code, message: "ต้องเปิดกะและเลือกคลังก่อนสแกนสินค้า" });
      return;
    }
    setRetailLookupBusy(true);
    setRetailVariantProduct(null);
    setSelectedRetailVariantId(null);
    setPendingRetailLine(null);
    try {
      const response = await productApi.retailLookup({ code, location_id: currentShift.location_id, qty });
      const result = response.data.data;
      if (result.result === "not_found" || !result.product) {
        setRetailException({
          kind: "not_found",
          code,
          message: result.error_code === "ambiguous_code"
            ? "รหัสนี้ตรงกับสินค้ามากกว่าหนึ่งรายการ Server จึงบล็อกไว้"
            : "ไม่พบบาร์โค้ดหรือ SKU ใน Retail Catalog ของ Brand นี้",
        });
        return;
      }
      let sourceProduct = source ?? eligibleProducts.find((item) => item.id === result.product?.id);
      if (!sourceProduct) {
        const catalogResponse = await productApi.list({
          search: code,
          is_active: true,
          catalog_scope: "retail_sale",
          page: 1,
          limit: 20,
        });
        const signedRows = catalogResponse.data.data as ProductListItem[];
        sourceProduct = signedRows.find((item) => item.id === result.product?.id);
      }
      if (!sourceProduct) {
        setRetailException({ kind: "permission", code, message: "สินค้าอยู่นอก Catalog ที่ Server ลงนามให้ Counter นี้" });
        return;
      }
      if (result.result === "variant_required") {
        setRetailVariantProduct(result.product);
        setSelectedRetailVariantId(null);
        setRetailException({ kind: "variant_required", code, message: "เลือก Variant ที่ต้องการก่อนเพิ่มลงตะกร้า" });
        return;
      }
      if (result.result === "unavailable") {
        setRetailException({
          kind: "unavailable",
          code,
          message: `${result.product.name} ไม่มี Stock ที่ขายได้ในคลังของกะนี้`,
        });
        return;
      }
      await validateRetailLine(result.product, sourceProduct, null, qty);
    } catch (error) {
      const message = getErrorMessage(error);
      setRetailException({
        kind: /permission|required|context/i.test(message) ? "permission" : "error",
        code,
        message,
      });
    } finally {
      setRetailLookupBusy(false);
    }
  }

  async function handleProductCodeLookup(rawKeyword: string): Promise<void> {
    const keyword = rawKeyword.trim().toLowerCase();
    if (!keyword) {
      return;
    }
    if (isRetailMode && (!retailContextValid || !catalogCacheTrusted)) {
      toast({
        title: "ยังสแกนสินค้าไม่ได้",
        description: "รอ Server ยืนยัน Retail Catalog ของ Company / Brand / Branch นี้ก่อน",
        variant: "destructive",
      });
      return;
    }
    if (isRetailMode) {
      await handleRetailLookup(rawKeyword);
      return;
    }
    let candidate =
      visibleProducts.find((item) => item.barcode?.toLowerCase() === keyword || item.sku.toLowerCase() === keyword) ??
      eligibleProducts.find((item) => item.barcode?.toLowerCase() === keyword || item.sku.toLowerCase() === keyword);
    if (!candidate && isOnline) {
      const response = await productApi.list({
        search: keyword,
        is_active: true,
        catalog_scope: catalogScope,
        page: 1,
        limit: 20,
      });
      const rows = response.data.data as ProductListItem[];
      candidate = rows.find((item) => item.barcode?.toLowerCase() === keyword || item.sku.toLowerCase() === keyword);
    }
    if (candidate) {
      addToCart(candidate);
      setSearch("");
      toast({ title: "เพิ่มสินค้าสำเร็จ", description: `${candidate.name} ถูกเพิ่มเข้าตะกร้าแล้ว` });
      return;
    }
    toast({ title: "ไม่พบสินค้า", description: `ไม่พบบาร์โค้ดหรือ SKU: ${rawKeyword}` });
  }

  function handleProductSelection(product: ProductListItem, qty = 1): void {
    if (isRetailMode) {
      void handleRetailLookup(product.barcode?.trim() || product.sku, product, qty);
      return;
    }
    addToCart(product, qty);
  }

  async function handleBarcodeLookup(): Promise<void> {
    await handleProductCodeLookup(search);
  }

  function handleApplyReplacementPreset(): void {
    if (exchangeReplacementPlan.length === 0) {
      toast({ title: "ยังไม่มี preset ทดแทนที่เหมาะสม" });
      return;
    }
    let addedCount = 0;
    exchangeReplacementPlan.forEach((entry) => {
      if (!entry.candidate) {
        return;
      }
      const qty = Math.max(1, Math.floor(Number(entry.source.qty ?? 1)));
      addToCart(entry.candidate, qty);
      addedCount += 1;
    });
    if (addedCount === 0) {
      toast({ title: "ยังไม่มีสินค้าทดแทนที่พร้อมขาย" });
      return;
    }
    toast({
      title: "เติมสินค้าทดแทนอัตโนมัติแล้ว",
      description: `เพิ่มสินค้าแทน ${addedCount} รายการจาก preset ของบิลแลก`,
    });
  }

  async function handleSaveReplacementRule(
    source: NonNullable<ExchangeContextDraft["source_items"]>[number],
    candidate: ProductListItem,
  ): Promise<void> {
    if (isOnline && branchId && canManageCentralReplacementRules) {
      await branchApi.upsertReplacementRule(branchId, {
        source_product_id: source.product_id,
        replacement_product_id: candidate.id,
      });
      await centralReplacementRulesQuery.refetch();
      toast({
        title: "บันทึกกฎส่วนกลางแล้ว",
        description: `${source.product_name} -> ${candidate.name}`,
      });
      return;
    }
    const rule: ReplacementRuleDraft = {
      id: `${branchId ?? "all"}:${source.product_id}`,
      branch_id: branchId ?? null,
      source_product_id: source.product_id,
      source_product_name: source.product_name,
      replacement_product_id: candidate.id,
      replacement_product_name: candidate.name,
      created_at: Date.now(),
    };
    await db.replacementRules.put(rule);
    setReplacementRulesVersion((value) => value + 1);
    toast({
      title: "บันทึกกฎ local แล้ว",
      description: `${source.product_name} -> ${candidate.name}`,
    });
  }

  async function handleDeleteReplacementRule(sourceProductId: string, matchedSource: ReplacementPlanEntry["matchedSource"]): Promise<void> {
    if (matchedSource === "central" && isOnline && branchId && canManageCentralReplacementRules) {
      await branchApi.deleteReplacementRule(branchId, sourceProductId);
      await centralReplacementRulesQuery.refetch();
      toast({ title: "ลบกฎส่วนกลางแล้ว" });
      return;
    }
    const ruleId = `${branchId ?? "all"}:${sourceProductId}`;
    await db.replacementRules.delete(ruleId);
    setReplacementRulesVersion((value) => value + 1);
    toast({ title: matchedSource === "local" ? "ลบกฎ local แล้ว" : "ลบกฎสินค้าทดแทนแล้ว" });
  }

  async function handleOpenShift(): Promise<void> {
    if (!selectedLocationId || !isOnline || !pairedDevice) {
      toast({
        title: "ยังเปิดกะไม่ได้",
        description: !isOnline ? "ต้องออนไลน์เพื่อให้ Server ยืนยันกะ" : !pairedDevice ? "กรุณาจับคู่เครื่อง Counter ก่อน" : "กรุณาเลือกคลัง",
        variant: "destructive",
      });
      return;
    }
    try {
      const response = await posApi.openShift({
        location_id: selectedLocationId,
        opening_cash: openingCash,
        shift_type: "staff_cashier",
        idempotency_key: openShiftIdempotencyRef.current,
      });
      const shift = response.data.data;
      setCurrentShift(shift);
      window.localStorage.setItem(SHIFT_CACHE_KEY, JSON.stringify(shift));
      openShiftIdempotencyRef.current = `shift-open:${generateClientOrderId()}`;
      setShiftGateOpen(false);
      toast({ title: "Server ยืนยันเปิดกะแล้ว", description: `${shift.shift_number} · Counter ${shift.opened_device_code ?? pairedDevice.device_code}` });
    } catch (error) {
      toast({ title: "เปิดกะไม่สำเร็จ", description: error instanceof Error ? error.message : "ตรวจสอบ Counter และลองใหม่", variant: "destructive" });
    }
  }

  function handleShiftUpdated(shift: CashierShift): void {
    setCurrentShift(shift);
    window.localStorage.setItem(SHIFT_CACHE_KEY, JSON.stringify(shift));
  }

  function handleShiftClosed(shift: CashierShift): void {
    setCurrentShift(shift);
    window.localStorage.removeItem(SHIFT_CACHE_KEY);
    setCartItems([]);
    navigate("/admin");
  }

  function handleShiftHandover(shift: CashierShift): void {
    setCurrentShift(shift);
    window.localStorage.removeItem(SHIFT_CACHE_KEY);
    setCartItems([]);
    logout();
  }

  function handleOrderDiscountChange(nextValue: number): void {
    const settings = branchSettingsQuery.data;
    if (!canApplyDiscount) {
      setOrderDiscount(0);
      toast({ title: "คุณไม่มีสิทธิ์ให้ส่วนลดใน POS" });
      return;
    }
    if (settings && !settings.pos_allow_discount) {
      setOrderDiscount(0);
      toast({ title: "สาขานี้ปิดการให้ส่วนลดไว้" });
      return;
    }
    const safeValue = Number.isFinite(nextValue) ? Math.max(0, nextValue) : 0;
    const branchLimit = settings ? (cart.subtotal * settings.pos_max_discount_pct) / 100 : safeValue;
    const maxDiscountAmount = canOverrideDiscount ? safeValue : branchLimit;
    setOrderDiscount(Math.min(safeValue, maxDiscountAmount));
  }

  function openPriceEditor(item: CartItem): void {
    setPriceEditProductId(item.product_id);
    setPriceEditVariantId(item.variant_id);
    setPriceEditValue((item.price_override?.requested_unit_price ?? item.original_price).toString());
    setPriceEditReason(item.price_override?.reason ?? "");
    setPriceEditReasonCode(item.price_override?.reason_code ?? "other");
    setPriceEditorOpen(true);
  }

  function handleApplyPriceOverride(): void {
    if (!priceEditProductId) {
      return;
    }
    const nextPrice = Number(priceEditValue);
    if (!Number.isFinite(nextPrice) || nextPrice < 0) {
      toast({ title: "กรอกราคาใหม่ไม่ถูกต้อง" });
      return;
    }
    if (priceEditReason.trim().length < 3) {
      toast({ title: "กรุณาระบุเหตุผลอย่างน้อย 3 ตัวอักษร" });
      return;
    }
    updateCartItem(priceEditProductId, (current) => ({
      ...current,
      unit_price: nextPrice,
      price_override: {
        requested_unit_price: nextPrice,
        reason_code: priceEditReasonCode,
        reason: priceEditReason.trim(),
      },
    }), priceEditVariantId);
    setPriceEditorOpen(false);
    setPriceEditProductId(null);
    setPriceEditVariantId(null);
    setPriceEditValue("");
    setPriceEditReason("");
    setPriceEditReasonCode("other");
    toast({ title: "บันทึกคำขอเปลี่ยนราคาแล้ว", description: "Server จะตรวจนโยบายและสิทธิ์อีกครั้งก่อนชำระเงิน" });
  }

  async function executeVoidSale(approvalToken?: string): Promise<void> {
    if (!voidOrder) return;
    await posApi.voidSale(voidOrder.id, voidReason.trim(), approvalToken);
    toast({ title: "Void บิลสำเร็จ", description: voidOrder.order_number });
    setVoidOrder(null);
    setVoidReason("");
    await recentSalesQuery.refetch();
  }

  async function handleVoidSale(): Promise<void> {
    if (!voidOrder || !voidReason.trim()) {
      toast({ title: "กรุณาระบุเหตุผลในการ void" });
      return;
    }
    if (!hasPermission("pos.sale.void")) {
      const orderId = voidOrder.id;
      const reason = voidReason.trim();
      setPendingManagerApproval({
        action: "pos.sale.void",
        requestPayload: { order_id: orderId, void_reason: reason },
        reason,
        description: `Void บิล ${voidOrder.order_number} ต้องได้รับอนุมัติจาก Manager`,
        onApproved: executeVoidSale
      });
      return;
    }
    try {
      await executeVoidSale();
    } catch (error) {
      toast({ title: "Void บิลไม่สำเร็จ", description: error instanceof Error ? error.message : "ลองใหม่อีกครั้ง" });
    }
  }

  function resetActiveSale(): void {
    setCartItems([]);
    setOrderDiscount(0);
    setPaymentMethod("cash");
    setPaidAmount(0);
    setCreditRef("");
    setQrDataUrl("");
    setPromptPayTarget("");
    setSplitPaymentEnabled(false);
    setSecondaryPaymentMethod("promptpay");
    setSecondaryPaymentAmount(0);
    setSecondaryPaymentReference("");
    setCustomerName("");
    setCustomerPhone("");
    setCustomerTaxId("");
    setCustomerSearch("");
    setDebouncedCustomerSearch("");
    setSelectedCustomer(null);
    setLoyaltyDiscount(0);
    setNote("");
    setExchangeContext(null);
    setResumedHoldDraft(null);
    setRetailException(null);
    setRetailVariantProduct(null);
    setPendingRetailLine(null);
    setPendingRetailQuote(null);
    checkoutIdRef.current = generateClientOrderId();
  }

  async function refreshHeldBills(): Promise<void> {
    setHeldBillsVersion((value) => value + 1);
  }

  function currentHoldDraft(label: string, id: string): HeldSaleDraft {
    if (!currentShift) throw new Error("ต้องเปิดกะก่อนพักบิล");
    return {
      id,
      shift_id: currentShift.id,
      location_id: currentShift.location_id,
      branch_id: branchId ?? null,
      sales_channel: isTakeawayMode ? "takeaway" : "walk_in",
      label,
      items: cart.items,
      order_discount: orderDiscount,
      loyalty_discount: loyaltyDiscount,
      payment_method: "cash",
      paid_amount: 0,
      payment_reference: null,
      split_payment_enabled: false,
      secondary_payment_method: "promptpay",
      secondary_payment_amount: 0,
      secondary_payment_reference: null,
      customer_name: customerName,
      customer_phone: "",
      customer_tax_id: "",
      customer_search: "",
      selected_customer: selectedCustomer,
      note,
      exchange_context: exchangeContext,
      held_at: Date.now(),
      sync_state: isOnline ? "pending_sync" : "local_only",
      server_backed: false,
    };
  }

  async function handleHoldBill(): Promise<boolean> {
    if (!currentShift || cart.items.length === 0) {
      return false;
    }
    if (isRetailMode && !isOnline) {
      toast({
        title: "Retail ต้องเชื่อมต่อ Server ก่อนพักบิล",
        description: "ไม่สร้าง Local shadow เพื่อป้องกันบิลซ้ำและข้อมูลราคาไม่ตรงกัน",
        variant: "destructive",
      });
      return false;
    }
    const defaultLabel = customerName.trim() || selectedCustomer?.display_name || `${cart.items[0]?.product_name ?? "บิล"} +${Math.max(cart.items.length - 1, 0)}`;
    const id = generateClientOrderId();
    const draft = currentHoldDraft(holdLabel.trim() || defaultLabel, id);
    setHeldBillsBusy("create");
    try {
      if (isOnline) {
        if (!hasPermission("pos.draft.create")) {
          throw new Error("คุณไม่มีสิทธิ์พักบิลบน Server");
        }
        await posApi.createHoldDraft(holdDraftPayload(draft, `hold:${id}`));
      } else {
        await db.heldBills.put(draft);
      }
      resetActiveSale();
      setHoldLabel("");
      setHoldCreateOpen(false);
      await refreshHeldBills();
      toast({
        title: "พักบิลแล้ว",
        description: isOnline ? `${draft.label} พร้อมเรียกต่อจากทุก Counter` : `${draft.label} อยู่ในเครื่องนี้และรอซิงก์`,
      });
      return true;
    } catch (error) {
      toast({
        title: "ยังพักบิลไม่สำเร็จ",
        description: `${getErrorMessage(error)} ตะกร้ายังอยู่ครบ`,
        variant: "destructive",
      });
      return false;
    } finally {
      setHeldBillsBusy(null);
    }
  }

  function restoreHeldCart(draft: HeldSaleDraft, items: CartItem[]): void {
    setCartItems(items.map(normalizeHeldCartItem));
    setOrderDiscount(draft.order_discount);
    setPaymentMethod("cash");
    setPaidAmount(0);
    setCreditRef("");
    setSplitPaymentEnabled(false);
    setSecondaryPaymentMethod("promptpay");
    setSecondaryPaymentAmount(0);
    setSecondaryPaymentReference("");
    setCustomerName(draft.customer_name);
    setCustomerPhone("");
    setCustomerTaxId("");
    setCustomerSearch("");
    setDebouncedCustomerSearch("");
    setSelectedCustomer(draft.selected_customer);
    setLoyaltyDiscount(isRetailMode ? 0 : draft.loyalty_discount);
    setNote(draft.note);
    setExchangeContext(draft.exchange_context ?? null);
    navigate(draft.sales_channel === "takeaway" ? "/pos?channel=takeaway" : "/pos", { replace: true });
  }

  async function resumeHeldBillNow(draft: HeldSaleDraft): Promise<void> {
    if (!currentShift) return;
    setHeldBillsBusy(draft.id);
    try {
      if (!draft.server_backed || !draft.server_id) {
        restoreHeldCart(draft, draft.items);
        await db.heldBills.delete(draft.id);
        setResumedHoldDraft(null);
      } else {
        if (!isOnline) throw new Error("เชื่อมต่อ Server ก่อนเรียกบิลจากทุก Counter");
        const claimKey = `claim:${draft.server_id}:${generateClientOrderId()}`;
        const claim = (await posApi.claimHoldDraft(draft.server_id, {
          expected_version: draft.version,
          idempotency_key: claimKey,
          shift_id: currentShift.id,
          location_id: currentShift.location_id,
        })).data.data as HoldDraftClaimResult;
        if (claim.requires_review) {
          setPendingRevalidation({ draft, claim });
          await refreshHeldBills();
          return;
        }
        await finalizeHeldResume(draft, claim, false);
        return;
      }
      await refreshHeldBills();
      setHeldBillsOpen(false);
      setPendingResumeDraft(null);
      toast({ title: "เรียกบิลกลับแล้ว", description: `${draft.label} พร้อมขายต่อ และจะตรวจราคาอีกครั้งตอนชำระ` });
    } catch (error) {
      const conflict = getHoldConflict(error);
      if (conflict) setHoldConflict(conflict);
      toast({ title: "เรียกบิลกลับไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
      await refreshHeldBills();
    } finally {
      setHeldBillsBusy(null);
    }
  }

  async function finalizeHeldResume(draft: HeldSaleDraft, claim: HoldDraftClaimResult, acceptRevalidation: boolean): Promise<void> {
    if (!currentShift || !draft.server_id) return;
    setHeldBillsBusy(draft.id);
    try {
      const resumed = (await posApi.resumeHoldDraft(draft.server_id, {
        expected_version: claim.draft.version,
        idempotency_key: `resume:${draft.server_id}:${generateClientOrderId()}`,
        claim_id: claim.draft.claim_id,
        shift_id: currentShift.id,
        location_id: currentShift.location_id,
        accept_revalidation: acceptRevalidation,
      })).data.data as ServerHoldDraft;
      restoreHeldCart(draft, claim.resume_cart.items);
      setResumedHoldDraft({ id: resumed.id, version: resumed.version });
      setPendingRevalidation(null);
      setPendingResumeDraft(null);
      setHeldBillsOpen(false);
      await refreshHeldBills();
      toast({ title: "เรียกบิลกลับแล้ว", description: `${draft.label} พร้อมขายต่อ และจะตรวจราคาอีกครั้งตอนชำระ` });
    } catch (error) {
      const conflict = getHoldConflict(error);
      if (conflict) setHoldConflict(conflict);
      toast({ title: "เรียกบิลกลับไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
      await refreshHeldBills();
    } finally {
      setHeldBillsBusy(null);
    }
  }

  async function rejectHeldRevalidation(): Promise<void> {
    const pending = pendingRevalidation;
    if (!pending?.draft.server_id || !currentShift) return;
    setHeldBillsBusy(pending.draft.id);
    try {
      await posApi.releaseHoldDraft(pending.draft.server_id, {
        expected_version: pending.claim.draft.version,
        idempotency_key: `release:${pending.draft.server_id}:${generateClientOrderId()}`,
        claim_id: pending.claim.draft.claim_id,
        shift_id: currentShift.id,
        reason: "Cashier rejected revalidation changes",
      });
      setPendingRevalidation(null);
      await refreshHeldBills();
    } catch (error) {
      const conflict = getHoldConflict(error);
      if (conflict) setHoldConflict(conflict);
      toast({ title: "ปล่อยสิทธิ์ไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    } finally {
      setHeldBillsBusy(null);
    }
  }

  async function handleResumeHeldBill(draft: HeldSaleDraft): Promise<void> {
    if (cart.items.length > 0) {
      setPendingResumeDraft(draft);
      return;
    }
    await resumeHeldBillNow(draft);
  }

  async function handleDeleteHeldBill(draft: HeldSaleDraft, reason: string): Promise<void> {
    setHeldBillsBusy(draft.id);
    try {
      if (draft.server_backed && draft.server_id) {
        await posApi.discardHoldDraft(draft.server_id, {
          expected_version: draft.version,
          idempotency_key: `discard:${draft.server_id}:${generateClientOrderId()}`,
          reason,
          shift_id: currentShift?.id,
        });
      } else {
        await db.heldBills.delete(draft.id);
      }
      await refreshHeldBills();
      toast({ title: "ยกเลิกบิลที่พักไว้แล้ว" });
    } catch (error) {
      const conflict = getHoldConflict(error);
      if (conflict) setHoldConflict(conflict);
      toast({ title: "ยกเลิกบิลไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    } finally {
      setHeldBillsBusy(null);
    }
  }

  async function handleReleaseHeldBill(draft: HeldSaleDraft): Promise<void> {
    if (!draft.server_id || !draft.claim_id || !currentShift) return;
    setHeldBillsBusy(draft.id);
    try {
      await posApi.releaseHoldDraft(draft.server_id, {
        expected_version: draft.version,
        idempotency_key: `release:${draft.server_id}:${generateClientOrderId()}`,
        claim_id: draft.claim_id,
        shift_id: currentShift.id,
        reason: "Operator released Hold Draft claim",
      });
      await refreshHeldBills();
      toast({ title: "ปล่อยสิทธิ์บิลแล้ว" });
    } catch (error) {
      const conflict = getHoldConflict(error);
      if (conflict) setHoldConflict(conflict);
      toast({ title: "ปล่อยสิทธิ์ไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    } finally {
      setHeldBillsBusy(null);
    }
  }

  async function handleReassignHeldBill(draft: HeldSaleDraft, assigneeUserId: string, reason: string): Promise<void> {
    if (!draft.server_id) return;
    setHeldBillsBusy(draft.id);
    try {
      await posApi.updateHoldDraft(draft.server_id, {
        expected_version: draft.version,
        idempotency_key: `reassign:${draft.server_id}:${generateClientOrderId()}`,
        assignee_user_id: assigneeUserId,
        reason,
      });
      await refreshHeldBills();
      toast({ title: "มอบหมายบิลแล้ว" });
    } catch (error) {
      const conflict = getHoldConflict(error);
      if (conflict) setHoldConflict(conflict);
      toast({ title: "มอบหมายไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    } finally {
      setHeldBillsBusy(null);
    }
  }

  async function handleReopenHeldBill(draft: HeldSaleDraft): Promise<void> {
    if (!draft.server_backed || !draft.server_id || !currentShift || !isOnline) return;
    setHeldBillsBusy(draft.id);
    try {
      await posApi.reopenHoldDraft(draft.server_id, {
        expected_version: draft.version,
        idempotency_key: `reopen:${draft.server_id}:${generateClientOrderId()}`,
        shift_id: currentShift.id,
        location_id: currentShift.location_id,
        reason: "Manual recovery from Hold Draft history",
      });
      await refreshHeldBills();
      toast({ title: "สร้างบิลกู้คืนแล้ว", description: "ตรวจราคาและรายการล่าสุดก่อนเรียกกลับ" });
    } catch (error) {
      const conflict = getHoldConflict(error);
      if (conflict) setHoldConflict(conflict);
      toast({ title: "กู้คืนบิลไม่สำเร็จ", description: getErrorMessage(error), variant: "destructive" });
    } finally {
      setHeldBillsBusy(null);
    }
  }

  async function queueOfflineSale(): Promise<void> {
    if (!currentShift || !branchId || !user) {
      return;
    }
    const pendingSale: PendingSale = {
      client_order_id: generateClientOrderId(),
      company_id: companyId ?? undefined,
      brand_id: brandId,
      branch_id: branchId,
      user_id: user.id,
      device_id: pairedDevice?.device_id ?? null,
      business_type: "restaurant",
      shift_id: currentShift.id,
      location_id: currentShift.location_id,
      items: cart.items,
      discount_amount: totalDiscount,
      customer_id: selectedCustomer?.id ?? null,
      discount_type: "amount",
      payment_method: paymentMethod,
      payments: checkoutPayments,
      payment_reference: paymentReference,
      paid_amount: currentPaidAmount,
      customer_name: customerName || selectedCustomer?.display_name || [selectedCustomer?.first_name, selectedCustomer?.last_name].filter(Boolean).join(" ") || null,
      customer_phone: customerPhone || selectedCustomer?.phone || null,
      customer_tax_id: customerTaxId || selectedCustomer?.tax_id || null,
      note: exchangeNote,
      exchange_context: exchangeContext,
      total_amount: finalTotal,
      change_amount: changeAmount,
      created_at: Date.now(),
      updated_at: Date.now(),
      synced: false,
      status: "pending",
      attempt_count: 0,
    };
    await db.pendingSales.put(pendingSale);
    await db.transaction("rw", db.stockBalances, async () => {
      for (const item of cart.items) {
        const key = `${item.product_id}:${item.variant_id ?? "base"}`;
        const balance = stockByProduct.get(key);
        if (!balance) {
          continue;
        }
        await db.stockBalances.update(balance.id, {
          qty_on_hand: Number(balance.qty_on_hand) - item.qty,
          qty_available: Number(balance.qty_available) - item.qty,
        });
      }
    });
    const offlineOrder = buildOfflineOrder(pendingSale, branchId, user.id);
    setLastOrder(offlineOrder);
    setShowReceipt(true);
    resetActiveSale();
    toast({ title: "บันทึกออฟไลน์แล้ว", description: "รายการขายถูกคิวไว้เพื่อ sync ภายหลัง" });
  }

  function buildPricingPayload(): Record<string, unknown> {
    return {
      items: cart.items.map((item) => ({
        product_id: item.product_id,
        variant_id: item.variant_id,
        qty: item.qty,
        discount_amount: item.discount_amount,
        discount_type: item.discount_type,
        expected_unit_price: item.original_price,
        ...(item.expected_price_version ? { expected_price_version: item.expected_price_version } : {}),
        ...(item.price_override ? { price_override: item.price_override } : {}),
      })),
      discount_amount: totalDiscount,
      discount_type: "amount",
      channel: "pos",
      currency: "THB",
      customer_id: selectedCustomer?.id ?? null,
      idempotency_key: `${checkoutIdRef.current}:price`,
      cart_version: 1,
    };
  }

  function buildCheckoutPayload(
    approvalToken?: string,
    priceOverrideApprovalToken?: string,
    quote?: PricingCalculation,
  ): Record<string, unknown> {
    if (!currentShift) return {};
    return {
        shift_id: currentShift.id,
        location_id: currentShift.location_id,
        items: cart.items.map((item) => ({
          product_id: item.product_id,
          variant_id: item.variant_id,
          qty: item.qty,
          unit_price: item.unit_price,
          original_price: item.original_price,
          discount_amount: item.discount_amount,
          discount_type: item.discount_type,
          vat_type: item.vat_type,
          vat_rate: item.vat_rate,
          ...(item.expected_price_version ? { expected_price_version: item.expected_price_version } : {}),
          ...(item.price_override ? { price_override: item.price_override } : {}),
        })),
        discount_amount: totalDiscount,
        discount_type: "amount",
        payment_method: paymentMethod,
        payments: checkoutPayments,
        payment_reference: paymentReference,
        paid_amount: currentPaidAmount,
        customer_name: customerName || selectedCustomer?.display_name || [selectedCustomer?.first_name, selectedCustomer?.last_name].filter(Boolean).join(" ") || null,
        customer_phone: customerPhone || selectedCustomer?.phone || null,
        customer_tax_id: customerTaxId || selectedCustomer?.tax_id || null,
        customer_id: selectedCustomer?.id ?? null,
        note: exchangeNote,
        client_order_id: checkoutIdRef.current,
        channel: "pos",
        currency: "THB",
        cart_version: quote?.cart_version ?? 1,
        ...(quote ? {
          pricing_quote_id: quote.quote_id,
          pricing_calculation_hash: quote.calculation_hash,
        } : {}),
        ...(approvalToken ? { approval_token: approvalToken } : {}),
        ...(priceOverrideApprovalToken ? { price_override_approval_token: priceOverrideApprovalToken } : {}),
        ...(resumedHoldDraft ? {
          source_hold_draft_id: resumedHoldDraft.id,
          source_hold_draft_version: resumedHoldDraft.version,
        } : {}),
    };
  }

  function acceptRetailServerPrice(): void {
    if (pendingRetailLine) {
      addRetailResolvedLine(pendingRetailLine);
      return;
    }
    if (pendingRetailQuote) {
      setCartItems((current) => current.map((item) => {
        const line = pendingRetailQuote.lines.find(
          (entry) => entry.product_id === item.product_id && entry.variant_id === item.variant_id,
        );
        if (!line) return item;
        const price = Number(line.authoritative_unit_price);
        return {
          ...item,
          unit_price: price,
          original_price: price,
          expected_price_version: line.price_version,
          subtotal: price * item.qty,
        };
      }));
      setPendingRetailQuote(null);
      setRetailException(null);
      checkoutIdRef.current = generateClientOrderId();
      window.setTimeout(() => searchRef.current?.focus(), 0);
    }
  }

  async function executeOnlineCheckout(
    approvalToken?: string,
    priceOverrideApprovalToken?: string,
    existingQuote?: PricingCalculation,
  ): Promise<void> {
      const quote = existingQuote ?? (await posApi.calculatePricing(buildPricingPayload())).data.data;
      const serverTotal = Number(quote.total_amount);
      const totalsDiffer = Math.abs(serverTotal - finalTotal) >= 0.01 || quote.has_price_discrepancy;
      if (!existingQuote && totalsDiffer) {
        if (isRetailMode) {
          const firstChangedLine = quote.lines.find((line) => line.discrepancy) ?? quote.lines[0];
          setPendingRetailQuote(quote);
          setRetailException({
            kind: "price_changed",
            code: firstChangedLine?.product_id ?? "retail-cart",
            message: "ยอดหรือราคาบิลเปลี่ยนหลัง Server ตรวจสอบ กรุณารับราคาล่าสุดแล้วตรวจบิลอีกครั้ง",
            previousPrice: finalTotal,
            serverPrice: serverTotal,
          });
          return;
        }
        const accepted = window.confirm(
          `ราคาจาก Server เปลี่ยนจาก ${formatThaiCurrency(finalTotal)} เป็น ${formatThaiCurrency(serverTotal)} ต้องการตรวจสอบและใช้ราคาใหม่หรือไม่?`
        );
        if (!accepted) return;
      }
      if (currentPaidAmount < serverTotal) {
        toast({
          title: "ยอดรับชำระไม่พอหลังตรวจราคากับ Server",
          description: `ยอดที่ต้องชำระ ${formatThaiCurrency(serverTotal)}`,
          variant: "destructive",
        });
        return;
      }
      const exactPayload = buildCheckoutPayload(approvalToken, priceOverrideApprovalToken, quote);
      if (Number(quote.discount_percentage) > cashierDiscountLimit && !canOverrideDiscount && !approvalToken) {
        setPendingManagerApproval({
          action: "pos.discount.override",
          requestPayload: exactPayload,
          reason: `ส่วนลด ${Number(quote.discount_percentage).toFixed(2)}% เกินเพดาน Cashier ${cashierDiscountLimit.toFixed(2)}%`,
          description: "ส่วนลดรวมทั้งส่วนลดสินค้า ส่วนลดบิล แต้ม และเครดิตเกินเพดาน Cashier",
          onApproved: (token) => executeOnlineCheckout(token, priceOverrideApprovalToken, quote),
        });
        return;
      }
      const selfApprovalAllowed = branchSettings?.pos_price_override_self_approval ?? false;
      if (
        quote.requires_price_override_approval
        && !priceOverrideApprovalToken
        && !(canApprovePriceOverride && selfApprovalAllowed)
      ) {
        setPendingManagerApproval({
          action: "pos.price.override",
          requestPayload: exactPayload,
          reason: cart.items.map((item) => item.price_override?.reason).filter(Boolean).join("; "),
          description: "ราคาที่ขอเปลี่ยนเกินเกณฑ์อัตโนมัติ ต้องได้รับอนุมัติจาก Manager คนอื่น",
          onApproved: (token) => executeOnlineCheckout(approvalToken, token, quote),
        });
        return;
      }
      const response = await posApi.createSale(exactPayload);
      const order = response.data.data as SaleOrder;
      setLastOrder(order);
      setShowReceipt(true);
      resetActiveSale();
      await db.completedOrders.put({ ...order, synced_at: Date.now() });
      await syncStockBalances(branchId ?? undefined);
      await queryClient.invalidateQueries({ queryKey: ["pos", "stock-balances"] });
      toast({ title: "ชำระเงินสำเร็จ" });
  }

  async function executeTakeawayCheckout(): Promise<void> {
    if (!currentShift || !takeawayMenuQuery.data) {
      throw new Error("ยังโหลดเมนูรับกลับและสิทธิ์ออฟไลน์ไม่สำเร็จ");
    }
    const result = await queueRestaurantOrder(undefined, {
      items: cart.items.map((item) => ({
        product_id: item.product_id,
        qty: Number(item.qty),
        special_request: null,
      })),
      payment_method: paymentMethod,
      paid_amount: currentPaidAmount,
      payments: checkoutPayments,
      customer_name: customerName || selectedCustomer?.display_name || [selectedCustomer?.first_name, selectedCustomer?.last_name].filter(Boolean).join(" ") || null,
      customer_phone: customerPhone || selectedCustomer?.phone || null,
      customer_tax_id: customerTaxId || selectedCustomer?.tax_id || null,
      note: note.trim() || null,
      shift_id: currentShift.id,
      location_id: currentShift.location_id,
    }, takeawayMenuQuery.data);

    setTakeawayOrder(result.order);
    setTakeawayResultOpen(true);
    resetActiveSale();
    setTakeawayOutboxSummary(await getRestaurantOutboxSummary());
    if (result.status === "reconciled") {
      await syncStockBalances(branchId ?? undefined);
      await queryClient.invalidateQueries({ queryKey: ["pos", "stock-balances"] });
      toast({ title: "รับเงินและออกคิวสำเร็จ", description: `คิว ${result.order.queue_display ?? "-"} พร้อมพิมพ์สลิป` });
    } else if (result.status === "needs_review") {
      toast({ title: "เก็บรายการไว้แล้ว แต่ต้องตรวจสอบ", description: result.error ?? "ตรวจสอบกะ ราคา และสต๊อก", variant: "destructive" });
    } else {
      toast({ title: "บันทึกออเดอร์ในเครื่องแล้ว", description: `คิวออฟไลน์ ${result.order.queue_display ?? "-"} จะซิงก์อัตโนมัติ` });
    }
    if (result.order.recipe_stock_warnings?.length) {
      toast({
        title: "ออกคิวแล้ว แต่สต๊อกต้องตรวจสอบ",
        description: result.order.recipe_stock_warnings.join(" · "),
        variant: "destructive",
      });
    }
  }

  async function handleTakeawaySlip(type: "customer" | "kitchen"): Promise<void> {
    if (!takeawayOrder) return;
    setTakeawayPrintBusy(type);
    try {
      const updated = takeawayOrder.client_order_id
        ? await markRestaurantLocalSlip(takeawayOrder.client_order_id, type)
        : type === "customer"
          ? (await wapApi.markCustomerSlip(takeawayOrder.session_id)).data.data
          : (await wapApi.markKitchenSlip(takeawayOrder.session_id)).data.data;
      setTakeawayOrder(updated);
      setTakeawayPendingPrint(type);
      setTakeawayOutboxSummary(await getRestaurantOutboxSummary());
      if (type === "kitchen") {
        toast({ title: "ส่งเข้าครัวแล้ว", description: `คิว ${updated.queue_display ?? "-"} แสดงใน KDS แล้ว` });
      }
    } catch (error) {
      toast({
        title: type === "customer" ? "พิมพ์สลิปลูกค้าไม่ได้" : "ส่งออเดอร์เข้าครัวไม่ได้",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    } finally {
      setTakeawayPrintBusy(null);
    }
  }

  async function handleCheckout(): Promise<void> {
    if (!currentShift || cart.items.length === 0) {
      return;
    }
    if (!retailContextValid) {
      toast({
        title: "Retail context ไม่ครบ",
        description: "ต้องใช้ Company, Brand, Branch และ Retail target ที่ Server ลงนามก่อนขาย",
        variant: "destructive",
      });
      return;
    }
    setIsSubmitting(true);
    try {
      if (isTakeawayMode) {
        await executeTakeawayCheckout();
        return;
      }
      if (!isOnline) {
        toast({
          title: "ตะกร้านี้อยู่ในสถานะ Stale",
          description: "เชื่อมต่ออินเทอร์เน็ตเพื่อตรวจราคา VAT และสิทธิ์กับ Server ก่อนชำระเงิน",
          variant: "destructive"
        });
        return;
      }
      await executeOnlineCheckout();
    } catch (error) {
      toast({
        title: "ชำระเงินไม่สำเร็จ",
        description: loyaltyDiscount > 0
          ? "มีการใช้แต้มแล้วแต่การขายยังไม่สำเร็จ กรุณาตรวจรายการแต้มของลูกค้าก่อนลองใหม่"
          : (error instanceof Error ? error.message : "ลองใหม่อีกครั้ง"),
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  const quickAmounts = useMemo(() => {
    const exact = finalTotal;
    const ceil100 = Math.ceil(finalTotal / 100) * 100;
    const ceil500 = Math.ceil(finalTotal / 500) * 500;
    const ceil1000 = Math.ceil(finalTotal / 1000) * 1000;
    return [exact, ceil100, ceil500, ceil1000].filter((value, index, list) => list.indexOf(value) === index);
  }, [finalTotal]);
  const currentLocationName = useMemo(
    () => locations.find((location) => location.id === currentShift?.location_id)?.name ?? "ยังไม่เลือกคลัง",
    [currentShift?.location_id, locations],
  );
  const visibleLowStockCount = useMemo(
    () => visibleProducts.filter((product) => {
      const stock = getAvailableStock(product.id);
      return stock > 0 && stock <= 5;
    }).length,
    [visibleProducts, stockByProduct],
  );
  const paymentLabel = useMemo(() => {
    return paymentMethodLabels[paymentMethod] ?? "อื่นๆ";
  }, [paymentMethod]);
  const amountDue = Math.max(finalTotal - currentPaidAmount, 0);
  const heldBills = heldBillsQuery.data ?? [];
  const activeHeldBillCount = heldBills.filter((draft) => !draft.status || draft.status === "active" || draft.status === "claimed").length;
  const replacementRules = replacementRulesQuery.data ?? [];
  const recentSales = recentSalesQuery.data ?? [];
  const branchSettings = branchSettingsQuery.data;
  const staffIdentifier = user?.employee_code?.trim() || user?.username || "-";
  const staffDisplayName = user?.display_name?.trim() || user?.username || "-";
  const staffAuditLabel = `${staffDisplayName} · ID ${staffIdentifier}`;
  const canApplyDiscount = hasPermission("pos.discount.apply") || hasPermission("pos.discount.override");
  const canOverrideDiscount = hasPermission("pos.discount.override");
  const canApprovePriceOverride = hasPermission("pos.price.override");
  const canRequestPriceOverride = canApprovePriceOverride || hasPermission("pos.price.override.request");
  const canVoidSale = hasPermission("pos.sale.void") || hasPermission("pos.sale.void.request");
  const canRefundSale = hasPermission("pos.refund.create") || hasPermission("pos.refund.request");
  const canManageCentralReplacementRules = hasPermission("system.branch.edit");
  const canViewDevices = hasPermission("system.device.view");
  const canEditBranchSettings = hasPermission("system.branch.edit") || hasPermission("system.company.edit");
  const currentCounterDevice = pairedDevice?.branch_id === branchId && pairedDevice.device_type === "counter" ? pairedDevice : null;
  const cameraReady = typeof navigator.mediaDevices?.getUserMedia === "function";
  const discountAllowed = (branchSettings?.pos_allow_discount ?? true) && canApplyDiscount;
  const maxDiscountPct = branchSettings?.pos_max_discount_pct ?? 100;
  const maxDiscountAmount = (cart.subtotal * maxDiscountPct) / 100;
  const cashierDiscountLimit = branchSettings?.pos_cashier_discount_limit_pct ?? 10;
  const grossBeforeDiscount = cart.items.reduce(
    (sum, item) => sum + Number(item.original_price) * Number(item.qty),
    0
  );
  const netAfterDiscount = Math.max(cart.subtotal - totalDiscount, 0);
  const effectiveDiscountPct = grossBeforeDiscount > 0
    ? Math.max(0, ((grossBeforeDiscount - netAfterDiscount) * 100) / grossBeforeDiscount)
    : 0;
  const exchangeNote = useMemo(() => {
    if (!exchangeContext) {
      return note || null;
    }
    const creditLine = `Exchange credit used: ${formatThaiCurrency(exchangeCreditApplied)}${exchangeCreditRemaining > 0 ? `, remaining ${formatThaiCurrency(exchangeCreditRemaining)}` : ""}`;
    const combined = [note?.trim() || "", creditLine].filter(Boolean).join("\n");
    return combined || null;
  }, [exchangeContext, exchangeCreditApplied, exchangeCreditRemaining, note]);
  const replacementRuleMap = useMemo(
    () => new Map(replacementRules.map((rule) => [rule.source_product_id, rule])),
    [replacementRules],
  );
  const centralReplacementRuleMap = useMemo(
    () => new Map((centralReplacementRulesQuery.data ?? []).map((rule) => [rule.source_product_id, rule])),
    [centralReplacementRulesQuery.data],
  );
  const exchangeSuggestedProducts = useMemo(() => {
    if (!exchangeContext || products.length === 0) {
      return [] as ProductListItem[];
    }
    const sourceProductIds = new Set((exchangeContext.source_items ?? []).map((item) => item.product_id));
    const sourceTokens = new Set(
      (exchangeContext.source_items ?? exchangeContext.refunded_items.map((productName) => ({ product_id: "", product_name: productName })))
        .flatMap((item) => tokenizeSearchTerms(item.product_name))
    );
    if (sourceTokens.size === 0) {
      return [] as ProductListItem[];
    }
    return [...products]
      .map((product) => {
        if (sourceProductIds.has(product.id)) {
          return { product, score: -1 };
        }
        const haystack = `${product.name} ${product.sku} ${product.barcode ?? ""}`.toLowerCase();
        let score = 0;
        sourceTokens.forEach((token) => {
          if (haystack.includes(token)) {
            score += product.name.toLowerCase().includes(token) ? 2 : 1;
          }
        });
        return { product, score };
      })
      .filter((entry) => entry.score > 0)
      .sort((left, right) => right.score - left.score)
      .slice(0, 6)
      .map((entry) => entry.product);
  }, [exchangeContext, products]);
  const exchangeReplacementPlan = useMemo(() => {
    if (!exchangeContext?.source_items?.length || products.length === 0) {
      return [] as ReplacementPlanEntry[];
    }
    return exchangeContext.source_items.map((sourceItem) => {
      const centralRule = centralReplacementRuleMap.get(sourceItem.product_id);
      const centralCandidate = centralRule
        ? products.find((product) => product.id === centralRule.replacement_product_id && getAvailableStock(product.id) > 0) ?? null
        : null;
      if (centralCandidate) {
        return { source: sourceItem, candidate: centralCandidate, matchedSource: "central" as const };
      }
      const localRule = replacementRuleMap.get(sourceItem.product_id);
      const localCandidate = localRule
        ? products.find((product) => product.id === localRule.replacement_product_id && getAvailableStock(product.id) > 0) ?? null
        : null;
      if (localCandidate) {
        return { source: sourceItem, candidate: localCandidate, matchedSource: "local" as const };
      }
      const sourceProduct = products.find((product) => product.id === sourceItem.product_id);
      const sourceTokens = tokenizeSearchTerms(sourceItem.product_name);
      const sourcePrice = sourceProduct ? Number(sourceProduct.selling_price ?? 0) : 0;
      const bestCandidate = [...products]
        .filter((product) => product.id !== sourceItem.product_id && getAvailableStock(product.id) > 0)
        .map((product) => {
          const productTokens = tokenizeSearchTerms(product.name);
          const sharedTokens = sourceTokens.filter((token) => productTokens.includes(token)).length;
          const sameCategory = sourceProduct?.category_id && sourceProduct.category_id === product.category_id ? 3 : 0;
          const priceDelta = sourcePrice > 0 ? Math.abs(Number(product.selling_price ?? 0) - sourcePrice) / sourcePrice : 1;
          const priceScore = sourcePrice > 0 ? Math.max(0, 2 - priceDelta * 4) : 0;
          return {
            product,
            score: sameCategory + sharedTokens * 2 + priceScore,
          };
        })
        .sort((left, right) => right.score - left.score)
        .find((entry) => entry.score > 0)?.product ?? null;

      return { source: sourceItem, candidate: bestCandidate, matchedSource: "suggested" as const };
    });
  }, [centralReplacementRuleMap, exchangeContext, products, replacementRuleMap, stockByProduct]);

  function openWorkspace(path: string, label: string): void {
    if (cart.items.length > 0 && !window.confirm(`มีสินค้าอยู่ในตะกร้า กรุณาพักบิลก่อนออกจากหน้าขาย\nต้องการไปที่ ${label} ต่อหรือไม่`)) {
      return;
    }
    if (cart.items.length > 0 && path.startsWith("/pos")) {
      resetActiveSale();
    }
    navigate(path);
  }

  return (
    <div data-pos-touch-surface className="flex min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(251,191,36,0.16),_transparent_28%),linear-gradient(180deg,_#fffaf0_0%,_#f8fafc_42%,_#eef2ff_100%)] md:h-screen">
      <div className="flex min-w-0 flex-1 flex-col md:overflow-hidden">
        {/* Tablet v2: compact identity and health header */}
        <div className="border-b border-slate-200/80 bg-white/90 px-4 py-2.5 backdrop-blur">
          <div className="flex flex-wrap items-center gap-2 lg:flex-nowrap">
            <div className="flex shrink-0 items-center gap-2">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-600 text-base font-black text-white shadow-sm" aria-hidden="true">F</span>
              <span className="hidden whitespace-nowrap text-base font-black text-blue-700 xl:inline">{PLATFORM_BRAND.productName}</span>
              <span className="hidden h-7 w-px bg-slate-200 xl:block" aria-hidden="true" />
              <span className="whitespace-nowrap text-base font-black text-slate-900">{isRetailMode ? "Retail POS" : "ขายหน้าร้าน"}</span>
            </div>
            <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto text-xs">
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 font-medium text-slate-700">{branchName}</span>
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 font-medium text-slate-600">
                {isRetailMode ? (currentCounterDevice?.device_code ?? "Counter ยังไม่จับคู่") : currentLocationName}
              </span>
              {currentShift ? (
                <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 font-medium text-emerald-700">
                  {currentShift.shift_number}
                </span>
              ) : null}
              <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-medium ${isTakeawayMode || isRetailMode ? "bg-amber-100 text-amber-800" : "bg-emerald-50 text-emerald-700"}`}>
                {isTakeawayMode ? <ShoppingBag className="h-3.5 w-3.5" /> : null}
                {isRetailMode ? "Pilot · Production ใช้ Legacy" : isTakeawayMode ? "รับกลับ · ออกคิว/KDS" : "ขายหน้าร้าน"}
              </span>
              {user ? (
                <span className="hidden items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 font-medium text-blue-700 xl:inline-flex">
                  <UserRoundCheck className="h-3.5 w-3.5" /> ID {staffIdentifier}
                </span>
              ) : null}
              {visibleLowStockCount > 0 && (
                <span className="rounded-full bg-amber-100 px-2.5 py-0.5 font-medium text-amber-700">
                  ⚠️ ใกล้หมด {visibleLowStockCount}
                </span>
              )}
              <span className={`rounded-full px-2.5 py-0.5 font-medium ${isOnline ? "bg-blue-50 text-blue-700" : "bg-red-100 text-red-700"}`}>
                {isOnline ? "●" : "○"} {isOnline ? "ONLINE" : "OFFLINE"}
              </span>
              {isTakeawayMode && takeawayOutboxSummary.pending + takeawayOutboxSummary.syncing + takeawayOutboxSummary.acknowledged + takeawayOutboxSummary.unknown > 0 ? (
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center gap-1 rounded-full bg-blue-50 px-3 py-1 font-medium text-blue-700 hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                  onClick={() => openWorkspace("/pos/offline-sync", "ศูนย์ซิงก์รายการขาย")}
                >
                  <CloudUpload className="h-3.5 w-3.5" /> รอผล {takeawayOutboxSummary.pending + takeawayOutboxSummary.syncing + takeawayOutboxSummary.acknowledged + takeawayOutboxSummary.unknown}
                </button>
              ) : null}
              {isTakeawayMode && takeawayOutboxSummary.needsReview + takeawayOutboxSummary.rejected + takeawayOutboxSummary.quarantined > 0 ? (
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center gap-1 rounded-full bg-red-50 px-3 py-1 font-medium text-red-700 hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                  onClick={() => openWorkspace("/pos/offline-sync", "ศูนย์ซิงก์รายการขาย")}
                >
                  <AlertTriangle className="h-3.5 w-3.5" /> ตรวจสอบ {takeawayOutboxSummary.needsReview + takeawayOutboxSummary.rejected + takeawayOutboxSummary.quarantined}
                </button>
              ) : null}
            </div>
            <div className="ml-auto flex shrink-0 items-center gap-1.5">
              {isRetailMode ? (
                <Button size="sm" variant="outline" className="min-h-11" onClick={() => openWorkspace("/pos/offline-sync", "ศูนย์สถานะและการกู้คืน")}>
                  <CloudUpload className="h-4 w-4" />สถานะซิงก์
                </Button>
              ) : null}
              {isRetailMode && canViewDevices ? (
                <Button size="sm" variant="outline" className="min-h-11" onClick={() => openWorkspace("/devices/uat-readiness", "Counter Readiness")}>
                  <TabletSmartphone className="h-4 w-4" />ความพร้อม
                </Button>
              ) : null}
              <Button size="sm" variant="outline" onClick={() => setRecentSalesOpen(true)} disabled={!currentShift}>
                ศูนย์บิล
              </Button>
              <Button size="sm" variant="outline" className="min-h-11" onClick={() => setCloseShiftOpen(true)} disabled={!currentShift}>จัดการกะ</Button>
              <Button size="sm" variant="outline" aria-label="สถานะเครื่องและการพิมพ์" onClick={() => setDeviceStatusOpen(true)}>
                <MonitorCog className="h-4 w-4" />
              </Button>
              <Button
                size="sm"
                variant="outline"
                aria-label="กลับหน้าผู้ดูแล"
                onClick={() => openWorkspace("/admin", "หน้าผู้ดูแล")}
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        <PosWorkspaceNav
          mode={isRetailMode ? "retail" : "restaurant"}
          heldBillCount={activeHeldBillCount}
          holdEnabled
          onHeldBills={() => setHeldBillsOpen(true)}
          onBillCenter={() => setRecentSalesOpen(true)}
          onShift={() => setCloseShiftOpen(true)}
          onDeviceStatus={() => setDeviceStatusOpen(true)}
          onNavigate={openWorkspace}
        />

        <div className="flex min-h-0 flex-1 flex-col md:flex-row md:overflow-hidden">
          <div className="flex min-w-0 flex-1 flex-col p-3 md:overflow-hidden md:p-4">
            <div className="rounded-[28px] border border-white/80 bg-white/85 p-4 shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-400" />
                  <input
                    ref={searchRef}
                    className="h-12 w-full rounded-xl border border-slate-300 bg-white pl-10 pr-4 text-sm shadow-sm"
                    placeholder={isRetailMode ? "สแกนบาร์โค้ด / ค้นหาชื่อ / SKU" : "ค้นหาสินค้า / สแกนบาร์โค้ด / ยิง QR"}
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void handleBarcodeLookup();
                      }
                    }}
                    autoFocus
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="h-11 rounded-xl px-4"
                    onClick={() => {
                      setScannerError("");
                      setScannerOpen(true);
                    }}
                  >
                    <Camera className="mr-2 h-4 w-4" />
                    เปิดกล้องสแกน
                  </Button>
                  <div className="flex items-center rounded-xl border border-slate-200 bg-slate-50 px-4 text-xs text-slate-500">
                    Enter = เพิ่มสินค้า, F1 = โฟกัสค้นหา, F2 = ช่องเงินสด
                  </div>
                </div>
              </div>
            </div>

            {isTakeawayMode ? (
              <div className={`mt-3 rounded-2xl border px-4 py-3 text-sm ${takeawayMenuQuery.isError ? "border-red-200 bg-red-50 text-red-800" : "border-orange-200 bg-orange-50 text-orange-900"}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold">โหมดรับกลับ — รับเงิน ออกเลขคิว และส่งรายการเข้า KDS</div>
                    <div className="mt-1 text-xs opacity-80">
                      {takeawayMenuQuery.isLoading
                        ? "กำลังโหลดเมนูและสิทธิ์ออฟไลน์"
                        : takeawayMenuQuery.isError
                          ? "โหลดเมนูรับกลับไม่สำเร็จ กรุณากดโหลดใหม่ก่อนรับเงิน"
                          : `พร้อมขาย ${takeawayMenuQuery.data?.products.filter((product) => product.is_available).length ?? 0} เมนู${isOnline ? "" : " · เก็บออเดอร์รอซิงก์ได้"}`}
                    </div>
                  </div>
                  {takeawayMenuQuery.isError ? (
                    <Button size="sm" variant="outline" onClick={() => void takeawayMenuQuery.refetch()}>โหลดใหม่</Button>
                  ) : null}
                </div>
              </div>
            ) : null}

            {isRetailMode ? (
              <div className={`mt-3 rounded-2xl border px-4 py-3 text-sm ${retailContextValid ? "border-blue-200 bg-blue-50 text-blue-900" : "border-red-200 bg-red-50 text-red-800"}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold">Retail Scan-first · Pilot</div>
                    <div className="mt-1 text-xs opacity-80">
                      {retailContextValid
                        ? "Catalog ถูกจำกัดด้วย signed Company / Brand / Branch · ระบบจริงยังใช้ Legacy data source"
                        : "Signed Retail context ไม่ครบ — ปิดการขายและไม่อ่าน Catalog จาก cache อื่น"}
                    </div>
                  </div>
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold shadow-sm">
                    {isOnline ? "Online" : "Offline"} · {catalogCacheTrusted ? "Catalog ตรงบริบท" : "รอ Catalog"}
                  </span>
                </div>
              </div>
            ) : null}

            {isRetailMode && retailLookupBusy ? (
              <div role="status" aria-live="polite" className="mt-3 flex items-center gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
                <Loader2 className="h-4 w-4 animate-spin" /> Server กำลังตรวจสินค้า ราคา และ Stock
              </div>
            ) : null}

            {isRetailMode && retailException ? (
              <section
                role="alert"
                aria-live="assertive"
                tabIndex={-1}
                className={`mt-3 rounded-2xl border px-4 py-4 text-sm ${retailException.kind === "price_changed" ? "border-amber-300 bg-amber-50 text-amber-950" : "border-red-200 bg-red-50 text-red-900"}`}
              >
                <div className="font-bold">
                  {retailException.kind === "not_found" ? "ไม่พบบาร์โค้ด"
                    : retailException.kind === "variant_required" ? "ต้องเลือก Variant"
                    : retailException.kind === "unavailable" ? "สินค้าหมด"
                    : retailException.kind === "stock_limit" ? "จำนวนเกิน Stock"
                    : retailException.kind === "price_changed" ? "ราคามีการเปลี่ยนแปลง"
                    : retailException.kind === "permission" ? "ไม่มีสิทธิ์หรือ Context ไม่ถูกต้อง"
                    : "ตรวจสินค้าไม่สำเร็จ"}
                </div>
                <div className="mt-1 font-mono text-xs opacity-70">{retailException.code}</div>
                <div className="mt-2">{retailException.message}</div>
                {retailException.kind === "price_changed" ? (
                  <div className="mt-3 grid gap-2 rounded-xl bg-white/80 p-3 sm:grid-cols-2">
                    <div><div className="text-xs text-slate-500">ราคาเดิมบนเครื่อง</div><div className="font-semibold">{formatThaiCurrency(retailException.previousPrice)}</div></div>
                    <div><div className="text-xs text-slate-500">ราคา Server</div><div className="font-semibold text-amber-800">{formatThaiCurrency(retailException.serverPrice)}</div></div>
                  </div>
                ) : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  {retailException.kind === "price_changed" ? (
                    <Button className="min-h-14 bg-amber-600 hover:bg-amber-700" onClick={acceptRetailServerPrice}>
                      ใช้ราคา Server {formatThaiCurrency(retailException.serverPrice)}
                    </Button>
                  ) : retailException.kind === "variant_required" ? (
                    <Button className="min-h-14" onClick={() => setRetailVariantProduct((current) => current)}>เลือก Variant</Button>
                  ) : retailException.kind === "permission" || retailException.kind === "error" ? (
                    <Button className="min-h-14" onClick={() => void handleRetailLookup(retailException.code)}>ตรวจใหม่กับ Server</Button>
                  ) : retailException.kind === "not_found" ? (
                    <Button
                      className="min-h-14"
                      onClick={() => {
                        setSearch(retailException.code);
                        window.setTimeout(() => { searchRef.current?.focus(); searchRef.current?.select(); }, 0);
                      }}
                    >
                      ค้นหาชื่อ / SKU
                    </Button>
                  ) : (
                    <Button
                      className="min-h-14"
                      onClick={() => {
                        setSearch("");
                        setRetailException(null);
                        window.setTimeout(() => searchRef.current?.focus(), 0);
                      }}
                    >
                      สแกนสินค้าอื่น
                    </Button>
                  )}
                  <button
                    type="button"
                    className="min-h-14 rounded-xl px-4 font-semibold text-slate-600 underline-offset-4 hover:underline"
                    onClick={() => {
                      setRetailException(null);
                      setPendingRetailLine(null);
                      setPendingRetailQuote(null);
                      setRetailVariantProduct(null);
                      window.setTimeout(() => searchRef.current?.focus(), 0);
                    }}
                  >
                    ยกเลิกและกลับไปสแกน
                  </button>
                </div>
              </section>
            ) : null}

            <div className="mt-3 flex min-h-0 flex-1 flex-col gap-3 lg:flex-row">
              <nav data-testid="pos-category-panel" aria-label="หมวดสินค้า" className="shrink-0 rounded-2xl border border-white/80 bg-white/80 p-2 shadow-sm lg:w-40 lg:overflow-y-auto">
                <div className="hidden px-2 pb-2 pt-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400 lg:block">หมวดสินค้า</div>
                <div className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-x-visible">
                  <button
                    type="button"
                    className={`min-h-11 shrink-0 rounded-xl px-4 py-2 text-left text-sm font-medium ${selectedCategory === "" ? "bg-blue-600 text-white" : "border border-slate-200 bg-white text-slate-700 hover:border-blue-300"}`}
                    onClick={() => setSelectedCategory("")}
                  >
                    ทั้งหมด
                  </button>
                  {categories.map((category) => (
                    <button
                      key={category.key}
                      type="button"
                      className={`min-h-11 shrink-0 rounded-xl px-4 py-2 text-left text-sm font-medium ${selectedCategory === category.key ? "bg-blue-600 text-white" : "border border-slate-200 bg-white text-slate-700 hover:border-blue-300"}`}
                      onClick={() => setSelectedCategory(category.key)}
                    >
                      {category.name}
                    </button>
                  ))}
                </div>
              </nav>

              <section data-testid="pos-product-panel" aria-label="รายการสินค้า" className="flex min-h-0 min-w-0 flex-1 flex-col lg:overflow-hidden">

            {isRetailMode && !retailContextValid ? (
              <div role="alert" className="mt-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-800">
                <div className="font-semibold">Permission / Context denied</div>
                <div className="mt-1">ออกจากระบบแล้วเข้า Retail POS ผ่าน Company App Launcher ใหม่ เพื่อรับ signed Brand และ Branch context</div>
              </div>
            ) : null}
            {isRetailMode && retailContextValid && !catalogCacheTrusted ? (
              <div role="status" className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
                <div className="font-semibold">{isOnline ? "กำลังโหลด Retail Catalog" : "Offline และไม่มี Catalog ของบริบทนี้"}</div>
                <div className="mt-1">{isOnline ? "ระบบจะเปิดสินค้าเมื่อ Server ยืนยัน Company / Brand / Branch แล้ว" : "เชื่อมต่ออินเทอร์เน็ตเพื่อรับ Catalog ก่อนเริ่มขาย"}</div>
              </div>
            ) : null}
            {isRetailMode && onlineSearchQuery.isError ? (
              <div role="alert" className="mt-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-800">
                <div className="font-semibold">โหลดผลค้นหาไม่สำเร็จ</div>
                <button type="button" className="mt-2 min-h-11 rounded-xl border border-red-300 bg-white px-4 font-semibold" onClick={() => void onlineSearchQuery.refetch()}>ลองใหม่อย่างปลอดภัย</button>
              </div>
            ) : null}

            {exchangeContext && exchangeSuggestedProducts.length > 0 ? (
              <div className="mt-4 rounded-[28px] border border-amber-200 bg-amber-50/80 p-4 shadow-[0_16px_40px_rgba(180,83,9,0.08)]">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.3em] text-amber-700">Replacement Ideas</div>
                    <div className="mt-1 text-lg font-semibold text-amber-950">สินค้าแนะนำสำหรับบิลแลก</div>
                    <div className="mt-1 text-sm text-amber-800">
                      เลือกจากรายการที่ชื่อใกล้เคียงกับสินค้าที่เพิ่งคืนได้ทันที
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      className="border-amber-300 bg-white text-amber-800"
                      onClick={() => {
                        const firstItem = exchangeContext.refunded_items[0];
                        if (firstItem) {
                          setSearch(firstItem);
                          setSearchTerm(firstItem);
                          searchRef.current?.focus();
                        }
                      }}
                    >
                      ค้นหาชื่อเดิม
                    </Button>
                    <Button
                      className="bg-amber-600 text-white hover:bg-amber-700"
                      onClick={handleApplyReplacementPreset}
                      disabled={exchangeReplacementPlan.every((entry) => !entry.candidate)}
                    >
                      เติมสินค้าทดแทนอัตโนมัติ
                    </Button>
                  </div>
                </div>
                {exchangeReplacementPlan.some((entry) => entry.candidate) ? (
                  <div className="mt-4 rounded-2xl border border-amber-200 bg-white/80 p-4">
                    <div className="text-xs font-semibold uppercase tracking-[0.25em] text-amber-700">Replacement Preset</div>
                    <div className="mt-3 space-y-3">
                      {exchangeReplacementPlan.map((entry) => (
                        <div key={`replacement-plan-${entry.source.product_id}`} className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 md:flex-row md:items-center md:justify-between">
                          <div className="min-w-0">
                            <div className="text-xs text-slate-500">คืนสินค้าเดิม</div>
                            <div className="font-medium text-slate-900">{entry.source.product_name} x{Math.max(1, Math.floor(Number(entry.source.qty ?? 1)))}</div>
                          </div>
                          {entry.candidate ? (
                            <div className="flex flex-col gap-2 md:items-end">
                              <div className="text-sm text-amber-800">
                                แนะนำแทนด้วย <span className="font-semibold">{entry.candidate.name}</span>
                                {entry.matchedSource === "central" ? <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700">กฎส่วนกลาง</span> : null}
                                {entry.matchedSource === "local" ? <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-[11px] font-medium text-blue-700">กฎ local</span> : null}
                              </div>
                              <div className="flex flex-wrap gap-2 md:justify-end">
                                <Button
                                  variant="outline"
                                  className="border-amber-300 bg-white text-amber-800"
                                  onClick={() => handleProductSelection(entry.candidate as ProductListItem, Math.max(1, Math.floor(Number(entry.source.qty ?? 1))))}
                                >
                                  เพิ่มสินค้าทดแทนนี้
                                </Button>
                                {entry.matchedSource === "suggested" ? (
                                  <Button
                                    variant="outline"
                                    className="border-slate-300 bg-white text-slate-700"
                                    onClick={() => void handleSaveReplacementRule(entry.source, entry.candidate as ProductListItem)}
                                  >
                                    {canManageCentralReplacementRules && isOnline ? "บันทึกเป็นกฎส่วนกลาง" : "จำเป็นตัวแทนหลักในเครื่องนี้"}
                                  </Button>
                                ) : (
                                  <Button
                                    variant="outline"
                                    className="border-slate-300 bg-white text-slate-700"
                                    onClick={() => void handleDeleteReplacementRule(entry.source.product_id, entry.matchedSource)}
                                  >
                                    {entry.matchedSource === "central" ? "ลบกฎส่วนกลาง" : "ล้างกฎ local"}
                                  </Button>
                                )}
                              </div>
                            </div>
                          ) : (
                            <div className="text-sm text-slate-500">
                              {centralReplacementRuleMap.get(entry.source.product_id)
                                ? "มีกฎส่วนกลางเดิมอยู่ แต่สินค้าทดแทนไม่พร้อมขายตอนนี้"
                                : replacementRuleMap.get(entry.source.product_id)
                                ? "มีกฎ local เดิมอยู่ แต่สินค้าทดแทนไม่พร้อมขายตอนนี้"
                                : "ยังไม่มีตัวแทนที่ตรงพอในระบบ"}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {exchangeSuggestedProducts.map((product) => {
                    const stock = getAvailableStock(product.id);
                    return (
                      <button
                        key={`exchange-suggestion-${product.id}`}
                        type="button"
                        disabled={stock <= 0}
                        onClick={() => handleProductSelection(product)}
                        className="rounded-2xl border border-amber-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="line-clamp-2 text-sm font-semibold text-slate-900">{product.name}</div>
                            <div className="mt-1 text-xs text-slate-500">{product.sku}</div>
                          </div>
                          <span className={`rounded-full px-2 py-1 text-[11px] font-medium ${stock <= 5 ? "bg-orange-100 text-orange-700" : "bg-green-100 text-green-700"}`}>
                            {stock <= 5 ? `เหลือ ${stock}` : "พร้อมขาย"}
                          </span>
                        </div>
                        <div className="mt-3 text-base font-semibold text-amber-700">{formatThaiCurrency(Number(product.selling_price))}</div>
                        <div className="mt-2 text-xs text-slate-500">กดเพื่อเพิ่มเป็นสินค้าทดแทน</div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {/* P5: Product Card Density — toggle bar */}
            {isRetailMode && retailContextValid && catalogCacheTrusted && !onlineSearchQuery.isLoading && visibleProducts.length === 0 ? (
              <div className="mt-3 rounded-2xl border border-dashed border-slate-300 bg-white/80 px-6 py-10 text-center text-sm text-slate-600">
                <div className="font-semibold text-slate-900">{searchTerm.trim() ? "ไม่พบสินค้าใน Retail Catalog" : "Retail Catalog ยังไม่มีสินค้าพร้อมขาย"}</div>
                <div className="mt-1">{searchTerm.trim() ? "ตรวจบาร์โค้ด ชื่อ หรือ SKU แล้วลองใหม่" : "ให้ผู้ดูแลเพิ่มสินค้าของ Brand นี้ก่อนเริ่มขาย"}</div>
              </div>
            ) : null}
            <div className="mt-3 flex items-center justify-between gap-2">
              <span className="text-xs text-slate-400">{visibleProducts.length} รายการ</span>
              <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-1">
                {(["normal", "compact", "list"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    title={mode === "normal" ? "การ์ดปกติ" : mode === "compact" ? "การ์ดย่อ" : "รายการ"}
                    onClick={() => {
                      setCardDensity(mode);
                      window.localStorage.setItem("pos-card-density", mode);
                    }}
                    className={`flex h-7 w-7 items-center justify-center rounded-lg transition-all ${
                      cardDensity === mode
                        ? "bg-blue-600 text-white shadow-sm"
                        : "text-slate-400 hover:text-slate-600"
                    }`}
                  >
                    {mode === "list"
                      ? <LayoutList className="h-4 w-4" />
                      : mode === "compact"
                        ? <span className="grid grid-cols-3 gap-0.5 p-0.5">{[...Array(6)].map((_, i) => <span key={i} className="h-1.5 w-1.5 rounded-sm bg-current" />)}</span>
                        : <LayoutGrid className="h-4 w-4" />}
                  </button>
                ))}
              </div>
            </div>

            {/* Product Grid — Normal Mode */}
            {cardDensity === "normal" && (
              <div className="mt-3 grid flex-1 auto-rows-max content-start grid-cols-2 gap-3 overflow-x-hidden overflow-y-auto xl:grid-cols-3 2xl:grid-cols-4">
                {visibleProducts.map((product) => {
                  const stock = getAvailableStock(product.id);
                  const stockLabel = stock <= 0 ? "หมด" : stock <= 5 ? "ใกล้หมด" : `${stock}`;
                  const stockStyle = stock <= 0 ? "bg-red-100 text-red-700" : stock <= 5 ? "bg-orange-100 text-orange-700" : "bg-green-100 text-green-700";
                  return (
                    <button
                      key={product.id}
                      type="button"
                      disabled={!isRetailMode && stock <= 0}
                      onClick={() => handleProductSelection(product)}
                      className="flex items-start gap-3 rounded-3xl border border-white/70 bg-white/90 p-4 text-left shadow-[0_16px_40px_rgba(15,23,42,0.08)] transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-[0_20px_48px_rgba(37,99,235,0.16)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-slate-100">
                        {product.image_url
                          ? <img src={product.image_url} alt={product.name} className="h-10 w-10 rounded-xl object-cover" />
                          : <ShoppingCart className="h-4 w-4 text-slate-400" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="line-clamp-2 text-sm font-medium text-slate-900">{product.name}</p>
                        <p className="mt-1 text-xs text-slate-400">{product.sku}</p>
                        <p className="mt-2 text-base font-semibold text-blue-600">{formatThaiCurrency(Number(product.selling_price))}</p>
                        <span className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${stockStyle}`}>{stockLabel}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Product Grid — Compact Mode (มากขึ้นต่อแถว) */}
            {cardDensity === "compact" && (
              <div className="mt-3 grid flex-1 auto-rows-max content-start grid-cols-3 gap-2 overflow-x-hidden overflow-y-auto lg:grid-cols-4 2xl:grid-cols-5">
                {visibleProducts.map((product) => {
                  const stock = getAvailableStock(product.id);
                  const outOfStock = stock <= 0;
                  const lowStock = stock > 0 && stock <= 5;
                  return (
                    <button
                      key={product.id}
                      type="button"
                      disabled={!isRetailMode && outOfStock}
                      onClick={() => handleProductSelection(product)}
                      className={`relative flex flex-col items-center rounded-2xl border bg-white/90 p-3 text-center shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 disabled:cursor-not-allowed disabled:opacity-40 ${
                        outOfStock ? "border-red-100" : lowStock ? "border-orange-200" : "border-white/70"
                      }`}
                    >
                      {/* Stock dot */}
                      {lowStock && (
                        <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-orange-400" />
                      )}
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100">
                        {product.image_url
                          ? <img src={product.image_url} alt={product.name} className="h-10 w-10 rounded-xl object-cover" />
                          : <ShoppingCart className="h-4 w-4 text-slate-400" />}
                      </div>
                      <p className="mt-2 line-clamp-2 w-full text-xs font-medium leading-tight text-slate-900">{product.name}</p>
                      <p className="mt-1.5 text-sm font-bold text-blue-600">{formatThaiCurrency(Number(product.selling_price))}</p>
                      {outOfStock && <p className="mt-1 text-[10px] text-red-500 font-medium">หมด</p>}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Product List — List Mode */}
            {cardDensity === "list" && (
              <div className="mt-3 flex-1 space-y-1.5 overflow-x-hidden md:overflow-y-auto">
                {visibleProducts.map((product) => {
                  const stock = getAvailableStock(product.id);
                  const outOfStock = stock <= 0;
                  const stockColor = outOfStock ? "text-red-500" : stock <= 5 ? "text-orange-500" : "text-emerald-600";
                  return (
                    <button
                      key={product.id}
                      type="button"
                      disabled={!isRetailMode && outOfStock}
                      onClick={() => handleProductSelection(product)}
                      className="flex w-full items-center gap-3 rounded-2xl border border-white/70 bg-white/90 px-4 py-3 text-left shadow-sm transition hover:border-blue-200 hover:bg-blue-50/40 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-slate-100">
                        {product.image_url
                          ? <img src={product.image_url} alt={product.name} className="h-9 w-9 rounded-xl object-cover" />
                          : <ShoppingCart className="h-3.5 w-3.5 text-slate-400" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-slate-900">{product.name}</p>
                        <p className="text-xs text-slate-400">{product.sku}{product.barcode ? ` · ${product.barcode}` : ""}</p>
                      </div>
                      <div className="flex flex-shrink-0 flex-col items-end gap-1">
                        <p className="text-sm font-bold text-blue-600">{formatThaiCurrency(Number(product.selling_price))}</p>
                        <p className={`text-[11px] font-medium ${stockColor}`}>
                          {outOfStock ? "หมด" : stock <= 5 ? `เหลือ ${stock}` : `${stock} ชิ้น`}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
              </section>
            </div>
          </div>

          <aside data-testid="pos-cart-panel" className="flex w-full flex-col overflow-y-auto border-t border-slate-200/80 bg-white/92 backdrop-blur md:h-full md:w-[22rem] md:max-h-none md:border-l md:border-t-0 lg:w-[25rem] xl:w-[28rem]">
            <div data-testid="pos-cart-header" className="sticky top-0 z-20 flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 py-4">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-slate-900">{isTakeawayMode ? "ตะกร้ารับกลับ" : "ตะกร้า"}</h2>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs">{cart.items.length}</span>
                {!isRetailMode ? (
                  <button
                    type="button"
                    className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700"
                    onClick={() => setHeldBillsOpen(true)}
                  >
                    พักไว้ {activeHeldBillCount}
                  </button>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                {!isRetailMode ? (
                  <button
                    type="button"
                    className="min-h-11 rounded-xl bg-amber-50 px-3 text-sm font-semibold text-amber-700 hover:bg-amber-100 disabled:opacity-40"
                    onClick={() => setHoldCreateOpen(true)}
                    disabled={cart.items.length === 0 || !currentShift}
                  >
                    พักบิล
                  </button>
                ) : null}
                <button
                  type="button"
                  className="min-h-11 rounded-xl border border-red-100 px-3 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-40"
                  disabled={cart.items.length === 0}
                  onClick={() => {
                    if (cart.items.length > 0 && !window.confirm("ยืนยันล้างรายการสินค้าในตะกร้าทั้งหมด?\nบิลนี้จะไม่ถูกพักไว้")) return;
                    resetActiveSale();
                  }}
                >
                  ล้างรายการ
                </button>
              </div>
            </div>

            <div data-testid="pos-cart-body" className="min-h-64 shrink-0 space-y-3 px-5 py-4">
              <div className="grid grid-cols-3 gap-2">
                <div className={`rounded-2xl border px-3 py-3 text-xs ${cart.items.length > 0 ? "border-blue-200 bg-blue-50 text-blue-700" : "border-slate-200 bg-slate-50 text-slate-500"}`}>
                  <div className="font-semibold uppercase tracking-[0.2em]">1</div>
                  <div className="mt-1">เลือกสินค้า</div>
                </div>
                <div className={`rounded-2xl border px-3 py-3 text-xs ${selectedCustomer || customerName || customerPhone ? "border-amber-200 bg-amber-50 text-amber-700" : "border-slate-200 bg-slate-50 text-slate-500"}`}>
                  <div className="font-semibold uppercase tracking-[0.2em]">2</div>
                  <div className="mt-1">ข้อมูลลูกค้า</div>
                </div>
                <div className={`rounded-2xl border px-3 py-3 text-xs ${finalTotal > 0 ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-500"}`}>
                  <div className="font-semibold uppercase tracking-[0.2em]">3</div>
                  <div className="mt-1">รับชำระเงิน</div>
                </div>
              </div>
              {exchangeContext ? (
                <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold">กำลังทำบิลแลกสินค้า</div>
                      <div className="mt-1 text-xs text-amber-700">
                        อ้างอิง {exchangeContext.source_order_number} • คืนแล้ว {formatThaiCurrency(exchangeContext.refund_amount)}
                      </div>
                      <div className="mt-1 text-xs text-amber-700">
                        {exchangeContext.refunded_items.length > 0 ? "สินค้าเดิมที่คืน:" : ""}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {exchangeContext.refunded_items.map((itemName) => (
                          <button
                            key={itemName}
                            type="button"
                            className="rounded-full border border-amber-300 bg-white px-3 py-1 text-xs text-amber-800"
                            onClick={() => {
                              setSearch(itemName);
                              setSearchTerm(itemName);
                              searchRef.current?.focus();
                            }}
                          >
                            {itemName}
                          </button>
                        ))}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="text-xs font-medium text-amber-700"
                      onClick={() => setExchangeContext(null)}
                    >
                      ปิดโหมดนี้
                    </button>
                  </div>
                </div>
              ) : null}
              {/* P3: Collapsible Customer Section */}
              <div className="rounded-xl border border-slate-200">
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-3 py-2.5 text-sm"
                  onClick={() => setCustomerSectionOpen((v) => !v)}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-700">ลูกค้า / ใบเสร็จ</span>
                    {selectedCustomer && (
                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                        👤 {selectedCustomer.display_name || [selectedCustomer.first_name, selectedCustomer.last_name].filter(Boolean).join(" ")}
                        {(selectedCustomer.points_balance ?? 0) > 0 ? ` · ⭐ ${selectedCustomer.points_balance}` : ""}
                      </span>
                    )}
                    {!selectedCustomer && customerName && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{customerName}</span>
                    )}
                  </div>
                  <span className="text-slate-400">{customerSectionOpen ? "▲" : "▼"}</span>
                </button>
                {customerSectionOpen && (
                  <div className="space-y-2 border-t border-slate-100 p-3">
                    <Input placeholder="ค้นหาสมาชิก (เบอร์โทร/ชื่อ)" value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} />
                    {(customerSearchQuery.data ?? []).length > 0 && !selectedCustomer ? (
                      <div className="space-y-1 rounded-lg border bg-slate-50 p-2">
                        {(customerSearchQuery.data ?? []).map((customer) => (
                          <button
                            key={customer.id}
                            type="button"
                            className="w-full rounded-md border bg-white px-3 py-2 text-left text-sm"
                            onClick={async () => {
                              const response = await crmApi.getCustomer(customer.id);
                              const fullCustomer = response.data.data as Customer;
                              setSelectedCustomer(fullCustomer);
                              setCustomerName(fullCustomer.display_name || [fullCustomer.first_name, fullCustomer.last_name].filter(Boolean).join(" "));
                              setCustomerPhone(fullCustomer.phone || "");
                              setCustomerTaxId(fullCustomer.tax_id || "");
                              setCustomerSearch("");
                              setDebouncedCustomerSearch("");
                              setCustomerSectionOpen(false);
                            }}
                          >
                            <div className="font-medium">{customer.customer_code} • {customer.display_name || "-"}</div>
                            <div className="text-xs text-slate-500">{maskPhone(customer.phone)} • {customer.tier_name || "-"} • {customer.points_balance} ⭐</div>
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {selectedCustomer ? (
                      <div className="flex items-center justify-between rounded-lg border bg-blue-50 px-3 py-2">
                        <div>
                          <div className="font-medium text-sm">{selectedCustomer.display_name || [selectedCustomer.first_name, selectedCustomer.last_name].filter(Boolean).join(" ")}</div>
                          <div className="text-xs text-slate-500">
                            {selectedCustomer.tier?.name ?? "-"} • {maskPhone(selectedCustomer.phone)} • แต้ม {selectedCustomer.points_balance} ⭐
                            {selectedCustomer.is_blacklisted ? " • ระงับสิทธิ์ Loyalty" : ""}
                          </div>
                        </div>
                        <button type="button" className="text-xs text-slate-500 hover:text-red-500"
                          onClick={() => { setSelectedCustomer(null); setLoyaltyDiscount(0); setCustomerSearch(""); setDebouncedCustomerSearch(""); }}>×</button>
                      </div>
                    ) : null}
                    <button type="button" className="text-xs text-blue-600" onClick={() => setCreateCustomerOpen(true)}>+ เพิ่มสมาชิกใหม่</button>
                    <div className="grid gap-2 pt-1">
                      <Input placeholder="ชื่อลูกค้า / ชื่อออกใบเสร็จ" value={customerName} onChange={(event) => setCustomerName(event.target.value)} />
                      <div className="grid grid-cols-2 gap-2">
                        <Input placeholder="เบอร์โทร" value={customerPhone} onChange={(event) => setCustomerPhone(event.target.value)} />
                        <Input placeholder="เลขผู้เสียภาษี" value={customerTaxId} onChange={(event) => setCustomerTaxId(event.target.value)} />
                      </div>
                      <textarea className="min-h-16 rounded-xl border border-slate-200 px-3 py-2 text-sm"
                        placeholder="หมายเหตุในบิล" value={note} onChange={(event) => setNote(event.target.value)} />
                    </div>
                  </div>
                )}
              </div>
              {cart.items.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center text-center text-slate-400">
                  <ShoppingCart className="mb-3 h-10 w-10" />
                  <p className="font-medium text-slate-600">ยังไม่มีสินค้าในบิล</p>
                  <p className="mt-1 max-w-56 text-xs">แตะสินค้าจากตรงกลาง หรือใช้กล้องสแกนบาร์โค้ดเพื่อเริ่มขาย</p>
                  <button type="button" className="mt-4 min-h-11 rounded-xl border border-slate-200 bg-white px-4 text-sm text-blue-600" onClick={() => setScannerOpen(true)}>
                    เปิดกล้องสแกน
                  </button>
                </div>
              ) : (
                cart.items.map((item) => (
                  /* P4: Compact Cart Items */
                  <div key={`${item.product_id}:${item.variant_id ?? "base"}`} className="rounded-xl border border-slate-200 px-3 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-slate-900 text-sm">{item.product_name}</p>
                        {item.variant_name ? <p className="text-xs text-slate-400">{item.variant_name}</p> : null}
                      </div>
                      <div className="flex flex-shrink-0 items-center gap-1.5">
                        {canRequestPriceOverride && !isTakeawayMode ? (
                          <button type="button" className="text-xs text-blue-500 hover:text-blue-700" onClick={() => openPriceEditor(item)}>
                            แก้
                          </button>
                        ) : null}
                        <button type="button" className="text-slate-300 hover:text-red-400" onClick={() => updateCartItem(item.product_id, () => null, item.variant_id)}>×</button>
                      </div>
                    </div>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1">
                        <button type="button" aria-label={`ลดจำนวน ${item.product_name}`} className="h-11 w-11 rounded-xl border border-slate-200 text-lg text-slate-700 hover:bg-slate-50"
                          onClick={() => updateCartQuantity(item, item.qty - 1)}>
                          −
                        </button>
                        <input aria-label={`จำนวน ${item.product_name}`} type="number" className="h-11 w-14 rounded-xl border border-slate-200 text-center text-base font-semibold"
                          value={item.qty} min={1} max={getAvailableStock(item.product_id, item.variant_id)}
                          onChange={(e) => updateCartQuantity(item, Number(e.target.value))} />
                        <button type="button" aria-label={`เพิ่มจำนวน ${item.product_name}`} className="h-11 w-11 rounded-xl border border-slate-200 text-lg text-slate-700 hover:bg-slate-50"
                          onClick={() => updateCartQuantity(item, item.qty + 1)}>
                          +
                        </button>
                      </div>
                      <p className="font-semibold text-sm text-slate-900">{formatThaiCurrency(item.qty * item.unit_price)}</p>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* P1: Sticky Checkout Footer */}
            <div data-testid="pos-checkout-panel" className="shrink-0 space-y-4 border-t border-slate-200 bg-white/95 px-5 py-4 backdrop-blur shadow-[0_-4px_20px_rgba(0,0,0,0.06)]">
              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between"><span>ยอดรวม</span><span>{formatThaiCurrency(cart.subtotal)}</span></div>
                  <div className="flex items-center justify-between gap-3">
                    <span>ส่วนลด</span>
                    <Button
                      type="button"
                      className="h-11 min-w-28 justify-end"
                      variant="outline"
                      disabled={isTakeawayMode || !discountAllowed || cart.subtotal <= 0}
                      onClick={() => setDiscountWorkspaceOpen(true)}
                    >
                      {orderDiscount > 0 ? `- ${formatThaiCurrency(orderDiscount)}` : "กำหนดส่วนลด"}
                    </Button>
                  </div>
                  <div className="text-xs text-slate-500">
                    {isTakeawayMode
                      ? "โหมดรับกลับใช้ราคาเมนูกลาง เพื่อให้ยอดขาย สต๊อก และ KDS ตรงกัน"
                      : discountAllowed
                      ? canOverrideDiscount
                        ? "คุณมีสิทธิ์ override ส่วนลดได้"
                        : `ส่วนลดสูงสุด ${maxDiscountPct}% (${formatThaiCurrency(maxDiscountAmount)})`
                      : canApplyDiscount
                        ? "สาขานี้ปิดการให้ส่วนลดไว้"
                        : "คุณไม่มีสิทธิ์ให้ส่วนลดใน POS"}
                  </div>
                  {loyaltyDiscount > 0 ? <div className="flex justify-between text-emerald-700"><span>ส่วนลดแต้ม</span><span>- {formatThaiCurrency(loyaltyDiscount)}</span></div> : null}
                  {exchangeCreditApplied > 0 ? (
                    <div className="flex justify-between text-amber-700">
                      <span>เครดิตแลกสินค้า</span>
                      <span>- {formatThaiCurrency(exchangeCreditApplied)}</span>
                    </div>
                  ) : null}
                  {exchangeContext && exchangeCreditRemaining > 0 ? (
                    <div className="flex justify-between text-xs text-amber-700">
                      <span>เครดิตคงเหลือหลังบิลนี้</span>
                      <span>{formatThaiCurrency(exchangeCreditRemaining)}</span>
                    </div>
                  ) : null}
                  <div className="flex justify-between"><span>VAT ในสินค้า</span><span>{formatThaiCurrency(vatIncludedAmount)}</span></div>
                  {vatExcludedAmount > 0 ? <div className="flex justify-between"><span>VAT แยกนอก</span><span>{formatThaiCurrency(vatExcludedAmount)}</span></div> : null}
                  {vatExemptSubtotal > 0 ? <div className="flex justify-between text-slate-500"><span>สินค้ายกเว้น VAT</span><span>{formatThaiCurrency(vatExemptSubtotal)}</span></div> : null}
                  <div className="mt-3 rounded-2xl bg-blue-600 px-4 py-3 text-white shadow-sm">
                    <div className="text-xs uppercase tracking-[0.25em] text-blue-100">ยอดสุทธิ</div>
                    <div className="mt-1 text-2xl font-semibold">{formatThaiCurrency(finalTotal)}</div>
                  </div>
                </div>
              </div>
              {!isTakeawayMode && selectedCustomer && loyaltySettingsQuery.data?.enabled ? (
                isRetailMode ? (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                    <div className="font-semibold">Loyalty ยังไม่เปิดใน Retail Pilot</div>
                    <div className="mt-1 text-xs">แต้มจะไม่ถูกตัดจนกว่า Server รองรับ Reserve → Commit/Release พร้อม Sale แบบ atomic</div>
                  </div>
                ) : (
                  <Button variant="outline" onClick={() => setRedeemOpen(true)}>แลกแต้มส่วนลด</Button>
                )
              ) : null}

              <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-[0.25em] text-slate-500">ช่องทางชำระเงิน</div>
                    <div className="mt-1 text-lg font-semibold text-slate-900">{paymentLabel}</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 px-3 py-2 text-right text-xs text-slate-500">
                    <div>ค้างชำระ</div>
                    <div className="mt-1 text-sm font-semibold text-slate-900">{formatThaiCurrency(amountDue)}</div>
                    {exchangeCreditApplied > 0 ? (
                      <div className="mt-1 text-[11px] text-amber-700">ใช้เครดิตแลกแล้ว {formatThaiCurrency(exchangeCreditApplied)}</div>
                    ) : null}
                  </div>
                </div>

              <div className="grid grid-cols-2 gap-2">
                {(["cash", "promptpay", "credit_card", "bank_transfer", "other"] as PaymentMethod[]).map((method) => {
                  const retailBlocked = isRetailMode && method !== "cash";
                  return (
                    <button
                      key={method}
                      type="button"
                      disabled={retailBlocked}
                      aria-describedby={retailBlocked ? `retail-payment-${method}` : undefined}
                      className={`min-h-16 rounded-xl border px-3 py-2 text-sm ${paymentMethod === method ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-300 bg-white text-slate-700"} disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400`}
                      onClick={() => setPaymentMethod(method)}
                    >
                      <span className="block font-semibold">{method === "cash" ? "เงินสด" : method === "promptpay" ? "PromptPay" : method === "credit_card" ? "บัตรเครดิต" : method === "bank_transfer" ? "โอนเงิน" : "อื่นๆ"}</span>
                      {retailBlocked ? <span id={`retail-payment-${method}`} className="mt-1 block text-[10px]">รอ Provider/Policy UAT</span> : null}
                    </button>
                  );
                })}
              </div>
              {/* end payment method card */}
              </div>
              {/* P7: Split Payment — toggle button */}
              <div className="mt-3 rounded-2xl border border-slate-200">
                <button
                  type="button"
                  disabled={isRetailMode}
                  className={`flex min-h-14 w-full items-center justify-between px-4 py-2.5 text-sm ${splitPaymentEnabled ? "text-amber-700" : "text-slate-600"} disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400`}
                  onClick={() => {
                    const next = !splitPaymentEnabled;
                    setSplitPaymentEnabled(next);
                    if (!next) {
                      setSecondaryPaymentAmount(0);
                      setSecondaryPaymentReference("");
                    }
                  }}
                >
                  <span className="font-medium">⇄ แยกชำระ 2 ช่องทาง</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs ${splitPaymentEnabled ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500"}`}>
                    {isRetailMode ? "รอ Provider UAT" : splitPaymentEnabled ? "เปิดอยู่" : "ปิด"}
                  </span>
                </button>
                {splitPaymentEnabled ? (
                  <div className="mt-3 space-y-3">
                    <div className="grid grid-cols-2 gap-2">
                      {(["promptpay", "credit_card", "bank_transfer", "other"] as PaymentMethod[]).map((method) => (
                        <button
                          key={method}
                          type="button"
                          className={`rounded-xl border px-3 py-2 text-sm ${secondaryPaymentMethod === method ? "border-amber-500 bg-amber-50 text-amber-700" : "border-slate-300 bg-white text-slate-700"}`}
                          onClick={() => setSecondaryPaymentMethod(method)}
                        >
                          {method === "promptpay" ? "PromptPay" : method === "credit_card" ? "บัตรเครดิต" : method === "bank_transfer" ? "โอนเงิน" : "อื่นๆ"}
                        </button>
                      ))}
                    </div>
                    <Input
                      type="number"
                      value={secondaryPaymentAmount}
                      onChange={(event) => setSecondaryPaymentAmount(Number(event.target.value))}
                      placeholder="ยอดชำระช่องทางที่ 2"
                    />
                    {secondaryPaymentMethod === "credit_card" || secondaryPaymentMethod === "bank_transfer" ? (
                      <Input
                        type="text"
                        value={secondaryPaymentReference}
                        onChange={(event) => setSecondaryPaymentReference(event.target.value)}
                        placeholder="เลขอ้างอิงช่องทางที่ 2"
                      />
                    ) : null}
                    <div className="text-xs text-slate-500">
                      ยอดคงเหลือของช่องทางหลัก: {formatThaiCurrency(primaryDueAmount)}
                    </div>
                  </div>
                ) : null}
              </div>

              {paymentMethod === "cash" ? (
                <div className="space-y-3 rounded-3xl border border-slate-200 bg-emerald-50/80 p-4">
                  <input
                    ref={cashInputRef}
                    type="number"
                    className="h-12 w-full rounded-xl border border-emerald-200 bg-white px-3 text-right text-xl font-semibold"
                    value={paidAmount}
                    onChange={(event) => setPaidAmount(Number(event.target.value))}
                  />
                  <div className="grid grid-cols-2 gap-2">
                    {quickAmounts.map((value) => (
                      <button
                        key={value}
                        type="button"
                        className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                        onClick={() => setPaidAmount(value)}
                      >
                        {formatThaiCurrency(value)}
                      </button>
                    ))}
                  </div>
                  <div className={`rounded-xl px-4 py-3 text-lg font-semibold ${currentPaidAmount >= finalTotal ? "bg-green-100 text-green-700" : "bg-red-50 text-red-700"}`}>
                    {currentPaidAmount >= finalTotal ? `เงินทอน: ${formatThaiCurrency(changeAmount)}` : `ยังขาด: ${formatThaiCurrency(amountDue)}`}
                  </div>
                </div>
              ) : null}

              {paymentMethod === "promptpay" ? (
                <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4 text-center">
                  {qrDataUrl ? <img src={qrDataUrl} alt="PromptPay QR" className="mx-auto h-48 w-48" /> : <WifiOff className="mx-auto h-10 w-10 text-slate-400" />}
                  <p className="mt-3 text-sm text-slate-500">ให้ลูกค้าสแกนยอด {formatThaiCurrency(promptPayAmount)}</p>
                  <p className="mt-1 text-xs text-slate-400">{promptPayTarget}</p>
                  <Button variant="outline" className="mt-3" onClick={() => setQrDataUrl("")}>รีเฟรช QR</Button>
                </div>
              ) : null}

              {paymentMethod === "credit_card" || paymentMethod === "bank_transfer" ? (
                <input
                  type="text"
                  className="h-11 w-full rounded-xl border border-slate-300 px-3"
                  placeholder={paymentMethod === "credit_card" ? "เลขอ้างอิงบัตร" : "เลขอ้างอิงการโอน"}
                  value={creditRef}
                  onChange={(event) => setCreditRef(event.target.value)}
                />
              ) : null}

              {isRetailMode ? (
                <div className="rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-xs text-blue-900">
                  <div className="font-semibold">Cash Pilot · Server-authoritative</div>
                  <div className="mt-1">ระบบจะตรวจ Pricing quote/version, สิทธิ์, Stock และ idempotency ก่อนบันทึก Sale</div>
                  <div className="mt-1 text-amber-800">เครื่องพิมพ์และลิ้นชักเงินสด: ยังไม่ยืนยัน Physical UAT</div>
                </div>
              ) : null}

              <Button
                className={`h-16 w-full rounded-2xl text-lg font-bold ${isRetailMode ? "bg-blue-600 hover:bg-blue-700" : "bg-green-600 hover:bg-green-700"}`}
                disabled={
                  cart.items.length === 0 ||
                  !currentShift ||
                  (isRetailMode && (!isOnline || !retailContextValid || !catalogCacheTrusted)) ||
                  (isRetailMode && paymentMethod !== "cash") ||
                  (isTakeawayMode && !takeawayMenuQuery.data) ||
                  (paymentMethod === "cash" && currentPaidAmount < finalTotal) ||
                  isSubmitting
                }
                onClick={() => void handleCheckout()}
              >
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {isTakeawayMode ? "รับเงินและออกคิว" : isRetailMode ? "ยืนยันรับเงิน" : "ชำระเงิน"} {formatThaiCurrency(finalTotal)}
              </Button>
              {isRetailMode ? (
                <div className="text-center text-xs text-slate-500">
                  {!retailContextValid
                    ? "ปิดรับชำระ: signed Retail context ไม่ครบ"
                    : !isOnline
                      ? "ปิดรับชำระ Offline จนกว่าจะมี signed Retail offline policy"
                      : !catalogCacheTrusted
                        ? "ปิดรับชำระระหว่างรอ Server ยืนยัน Catalog"
                        : "Server จะตรวจราคา สิทธิ์ สต๊อก และ idempotency ก่อนชำระ"}
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      </div>

      <Dialog
        open={Boolean(retailVariantProduct)}
        onOpenChange={(open) => {
          if (!open) {
            setRetailVariantProduct(null);
            setSelectedRetailVariantId(null);
            window.setTimeout(() => searchRef.current?.focus(), 0);
          }
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>เลือก Variant</DialogTitle>
            <DialogDescription>
              เลือกขนาดหรือรูปแบบที่ตรงกับสินค้า Server จะตรวจราคาและ Stock อีกครั้งก่อนเพิ่มลงตะกร้า
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            {(retailVariantProduct?.variants ?? []).map((variant) => {
              const available = Number(variant.available_qty);
              const selected = selectedRetailVariantId === variant.id;
              return (
                <button
                  key={variant.id}
                  type="button"
                  disabled={!variant.is_active || available <= 0}
                  aria-pressed={selected}
                  className={`min-h-14 rounded-2xl border p-4 text-left ${selected ? "border-blue-600 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white"} disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400`}
                  onClick={() => setSelectedRetailVariantId(variant.id)}
                >
                  <div className="font-semibold">{variant.name}</div>
                  <div className="mt-1 text-xs text-slate-500">{variant.sku}{variant.barcode ? ` · ${variant.barcode}` : ""}</div>
                  <div className="mt-2 flex items-center justify-between text-sm">
                    <span className="font-semibold text-blue-700">{formatThaiCurrency(Number(variant.server_price))}</span>
                    <span className={available > 0 ? "text-emerald-700" : "text-red-600"}>{available > 0 ? `ขายได้ ${available}` : "สินค้าหมด"}</span>
                  </div>
                </button>
              );
            })}
          </div>
          <DialogFooter>
            <Button
              className="min-h-14"
              disabled={!selectedRetailVariantId || retailLookupBusy}
              onClick={() => {
                const lookup = retailVariantProduct;
                const variant = lookup?.variants.find((item) => item.id === selectedRetailVariantId) ?? null;
                const source = lookup ? eligibleProducts.find((item) => item.id === lookup.id) : null;
                if (!lookup || !variant || !source) {
                  setRetailException({ kind: "permission", code: lookup?.sku ?? "variant", message: "Variant ไม่อยู่ใน signed Retail Catalog" });
                  return;
                }
                setRetailVariantProduct(null);
                setSelectedRetailVariantId(null);
                setRetailLookupBusy(true);
                void validateRetailLine(lookup, source, variant)
                  .catch((error) => setRetailException({ kind: "error", code: variant.sku, message: getErrorMessage(error) }))
                  .finally(() => setRetailLookupBusy(false));
              }}
            >
              {retailLookupBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {selectedRetailVariantId
                ? `เพิ่มลงตะกร้า ${formatThaiCurrency(Number(retailVariantProduct?.variants.find((item) => item.id === selectedRetailVariantId)?.server_price ?? 0))}`
                : "เลือก Variant ก่อน"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deviceStatusOpen} onOpenChange={setDeviceStatusOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><MonitorCog className="h-5 w-5" />สถานะเครื่องขายและการพิมพ์</DialogTitle>
            <DialogDescription>
              ตรวจสถานะเครือข่าย Counter กล้อง และการพิมพ์ก่อนเริ่มขาย โดยสถานะ Browser ไม่ถือเป็นผลทดสอบอุปกรณ์จริง
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className={`rounded-2xl border p-4 ${isOnline ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
              <div className="flex items-center gap-2 text-sm font-semibold"><Activity className="h-4 w-4" />เครือข่ายและการซิงก์</div>
              <div className={`mt-3 text-lg font-bold ${isOnline ? "text-emerald-700" : "text-red-700"}`}>{isOnline ? "ออนไลน์" : "ออฟไลน์ — ราคา Stale / ปิดชำระเงิน"}</div>
              <div className="mt-1 text-xs text-slate-500">ซิงก์ล่าสุด {lastSyncAt ? lastSyncAt.toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "ยังไม่มีข้อมูลรอบนี้"}</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold"><TabletSmartphone className="h-4 w-4" />อุปกรณ์ Counter</div>
              {currentCounterDevice ? (
                <>
                  <div className="mt-3 text-lg font-bold text-slate-900">{currentCounterDevice.name}</div>
                  <div className="mt-1 font-mono text-xs text-slate-500">{currentCounterDevice.device_code} · จับคู่กับสาขานี้</div>
                </>
              ) : (
                <>
                  <div className="mt-3 text-lg font-bold text-amber-700">โหมดผู้ใช้ทั่วไป</div>
                  <div className="mt-1 text-xs text-slate-500">ยังไม่ได้ล็อกเครื่องนี้ด้วย Counter Device ของสาขา</div>
                </>
              )}
            </div>
            <div className={`rounded-2xl border p-4 ${cameraReady ? "border-blue-200 bg-blue-50" : "border-amber-200 bg-amber-50"}`}>
              <div className="flex items-center gap-2 text-sm font-semibold"><Camera className="h-4 w-4" />กล้องและสแกนเนอร์</div>
              <div className={`mt-3 text-lg font-bold ${cameraReady ? "text-blue-700" : "text-amber-700"}`}>{cameraReady ? "พร้อมขอสิทธิ์กล้อง" : "อุปกรณ์นี้ไม่มีกล้องที่เว็บเข้าถึงได้"}</div>
              <div className="mt-1 text-xs text-slate-500">รองรับ QR, EAN, UPC, Code 39 และ Code 128</div>
            </div>
            <div className="rounded-2xl border border-violet-200 bg-violet-50 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold"><ClipboardList className="h-4 w-4" />ใบเสร็จและเครื่องพิมพ์</div>
              <div className="mt-3 text-lg font-bold text-violet-700">พิมพ์ผ่านระบบของอุปกรณ์</div>
              <div className="mt-1 text-xs text-slate-500">ตั้งไว้ {branchSettings?.receipt_copies ?? 1} สำเนา · สถานะเครื่องพิมพ์จริงต้องยืนยันบนอุปกรณ์</div>
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={autoPrintReceipt}
            className="flex min-h-14 w-full items-center justify-between rounded-2xl border border-slate-200 px-4 text-left"
            onClick={() => {
              const next = !autoPrintReceipt;
              setAutoPrintReceipt(next);
              window.localStorage.setItem("pos-auto-print-receipt", String(next));
            }}
          >
            <span><span className="block font-semibold text-slate-900">พิมพ์ใบเสร็จอัตโนมัติหลังชำระ</span><span className="block text-xs text-slate-500">ตั้งค่าเฉพาะเครื่องนี้และปิดไว้เป็นค่าเริ่มต้น</span></span>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${autoPrintReceipt ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{autoPrintReceipt ? "เปิด" : "ปิด"}</span>
          </button>
          <div className="rounded-xl bg-amber-50 px-4 py-3 text-xs text-amber-800">
            เว็บตรวจได้เฉพาะความพร้อมของกล้อง การเชื่อมต่อ และการตั้งค่าใบเสร็จ การยืนยันสาย LAN/Bluetooth/USB และกระดาษต้องทำกับเครื่องพิมพ์จริงใน UAT
          </div>
          <DialogFooter className="gap-2 sm:justify-between">
            <div className="flex flex-wrap gap-2">
              {canViewDevices ? <Button variant="outline" onClick={() => { setDeviceStatusOpen(false); openWorkspace("/devices", "จัดการอุปกรณ์"); }}>จัดการอุปกรณ์</Button> : null}
              {canEditBranchSettings && branchId ? <Button variant="outline" onClick={() => { setDeviceStatusOpen(false); openWorkspace(`/branches/${branchId}/settings`, "ตั้งค่าสาขาและใบเสร็จ"); }}>ตั้งค่าใบเสร็จ</Button> : null}
            </div>
            <Button
              disabled={!lastOrder}
              onClick={() => {
                setDeviceStatusOpen(false);
                setShowReceipt(true);
              }}
            >
              {lastOrder ? "เปิดใบเสร็จล่าสุดเพื่อทดสอบพิมพ์" : "ยังไม่มีใบเสร็จให้ทดสอบ"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={shiftGateOpen} onOpenChange={setShiftGateOpen}>
        <DialogContent className="max-w-3xl p-0">
          <div className="border-b border-slate-200 px-5 py-5 pr-16 md:px-7">
          <DialogHeader>
            <DialogTitle className="text-xl">เปิดกะพนักงานก่อนเริ่มขาย</DialogTitle>
            <DialogDescription>Server จะผูกพนักงาน สาขา คลัง และ Counter ให้เป็นกะเดียวกัน</DialogDescription>
          </DialogHeader>
          </div>
          <div className="space-y-5 p-5 md:p-7">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900"><p className="text-xs font-semibold text-blue-600">พนักงาน</p><p className="mt-1 font-bold">{staffDisplayName}</p><p className="text-xs">ID {staffIdentifier}</p></div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm"><p className="text-xs font-semibold text-slate-500">สาขา</p><p className="mt-1 font-bold text-slate-900">{branchName}</p></div>
              <div className={`rounded-2xl border p-4 text-sm ${pairedDevice ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-red-200 bg-red-50 text-red-800"}`}><p className="text-xs font-semibold">Counter</p><p className="mt-1 font-bold">{pairedDevice?.name ?? "ยังไม่จับคู่เครื่อง"}</p><p className="text-xs">{pairedDevice?.device_code ?? "ต้องจับคู่ก่อนเปิดกะ"}</p></div>
            </div>
            <section>
              <h3 className="text-sm font-bold text-slate-900">เลือกคลังที่ขาย</h3>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {locations.map((stockLocation) => <button key={stockLocation.id} type="button" onClick={() => setSelectedLocationId(stockLocation.id)} className={`min-h-14 rounded-xl border px-4 text-left text-sm font-semibold ${selectedLocationId === stockLocation.id ? "border-blue-600 bg-blue-50 text-blue-800 ring-2 ring-blue-100" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}>{stockLocation.name}</button>)}
              </div>
              {locations.length === 0 ? <div className="mt-2 rounded-xl bg-amber-50 p-4 text-sm text-amber-800">สาขานี้ยังไม่มีคลังสำหรับ POS</div> : null}
            </section>
            <section>
              <label className="text-sm font-bold text-slate-900">เงินทอนตั้งต้น</label>
              <div className="mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-2">
                <input aria-label="เงินทอนตั้งต้น" type="number" min={0} inputMode="decimal" className="h-14 w-full rounded-xl border border-slate-300 px-4 text-xl font-bold" value={openingCash} onChange={(event) => setOpeningCash(Math.max(0, Number(event.target.value) || 0))} />
                <div className="flex gap-2">{[500, 1000, 2000].map((amount) => <button key={amount} type="button" onClick={() => setOpeningCash(amount)} className="min-h-14 rounded-xl border border-slate-200 px-3 text-sm font-bold hover:bg-slate-50">฿{amount.toLocaleString()}</button>)}</div>
              </div>
            </section>
            {!isOnline ? <div className="flex min-h-12 items-center gap-2 rounded-xl bg-amber-50 px-4 text-sm font-semibold text-amber-800"><WifiOff className="h-5 w-5" />เปิดกะใหม่ไม่ได้ขณะ Offline</div> : null}
            <Button className="h-14 w-full text-base" onClick={() => void handleOpenShift()} disabled={!selectedLocationId || !isOnline || !pairedDevice}>ยืนยันเปิดกะกับ Server</Button>
          </div>
        </DialogContent>
      </Dialog>

      {currentShift ? (
        <CloseShiftDialog
          open={closeShiftOpen}
          onOpenChange={setCloseShiftOpen}
          shift={currentShift}
          online={isOnline}
          operatorLabel={staffAuditLabel}
          cashMovementApprovalThreshold={Number(branchSettingsQuery.data?.pos_cash_movement_approval_threshold ?? 1000)}
          varianceSoftThreshold={Number(branchSettingsQuery.data?.pos_shift_variance_soft_threshold ?? 100)}
          varianceApprovalThreshold={Number(branchSettingsQuery.data?.pos_shift_variance_approval_threshold ?? 500)}
          canCreateCashMovement={hasPermission("pos.cash_movement.create")}
          canHandover={hasPermission("pos.cashier.handover") && Boolean(pairedDevice)}
          onShiftUpdated={handleShiftUpdated}
          onClosed={handleShiftClosed}
          onHandover={handleShiftHandover}
        />
      ) : null}

      <Dialog open={showReceipt} onOpenChange={setShowReceipt}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>ใบเสร็จ</DialogTitle>
            <DialogDescription>
              รายละเอียดใบเสร็จจาก Server สำหรับตรวจสอบและพิมพ์ซ้ำ
            </DialogDescription>
          </DialogHeader>
          {lastOrder ? (
            <ReceiptView
              ref={receiptRef}
              order={lastOrder}
              company={{
                name: "Restaurant POS",
                phone: "0812345678",
                logo_url: branchSettingsQuery.data?.receipt_show_logo
                  ? branchSettingsQuery.data.receipt_logo_url
                  : undefined,
              }}
              branch={{ name: branchName }}
              cashier={user?.display_name ?? user?.username ?? "Cashier"}
            />
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => void handlePrint()}>พิมพ์</Button>
            <Button onClick={() => setShowReceipt(false)}>ขายต่อ</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={takeawayResultOpen} onOpenChange={setTakeawayResultOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>ออเดอร์รับกลับ</DialogTitle>
          </DialogHeader>
          {takeawayOrder ? (
            <div className="space-y-4">
              <div className="rounded-2xl bg-slate-950 p-5 text-center text-white">
                <div className="text-xs uppercase tracking-[0.25em] text-slate-400">Queue</div>
                <div className="mt-1 text-6xl font-black">{takeawayOrder.queue_display ?? "-"}</div>
                <div className="mt-2 text-sm text-slate-300">รับเงินแล้ว {formatThaiCurrency(Number(takeawayOrder.total_amount))}</div>
                {takeawayOrder.is_offline_pending ? (
                  <div className="mt-3 inline-flex rounded-full bg-amber-400/20 px-3 py-1 text-xs font-semibold text-amber-200">คิวออฟไลน์ · รอซิงก์</div>
                ) : (
                  <div className="mt-3 inline-flex rounded-full bg-emerald-400/20 px-3 py-1 text-xs font-semibold text-emerald-200">บันทึกบนเซิร์ฟเวอร์แล้ว</div>
                )}
              </div>
              <div className="max-h-48 space-y-2 overflow-y-auto rounded-2xl border border-slate-200 p-4">
                {takeawayOrder.items.map((item) => (
                  <div key={`${item.product_id}-${item.special_request ?? ""}`} className="flex items-start justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2">
                    <div>
                      <div className="font-medium text-slate-900">{item.product_name}</div>
                      {item.special_request ? <div className="text-xs text-slate-500">{item.special_request}</div> : null}
                    </div>
                    <div className="font-semibold text-slate-900">x{item.qty}</div>
                  </div>
                ))}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <Button
                  className="h-12"
                  onClick={() => void handleTakeawaySlip("customer")}
                  disabled={takeawayPrintBusy !== null}
                >
                  {takeawayPrintBusy === "customer" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Printer className="h-4 w-4" />}
                  {takeawayOrder.customer_slip_printed_at ? "พิมพ์สลิปลูกค้าซ้ำ" : "พิมพ์สลิปลูกค้า"}
                </Button>
                <Button
                  className="h-12 bg-orange-600 hover:bg-orange-700"
                  onClick={() => void handleTakeawaySlip("kitchen")}
                  disabled={takeawayPrintBusy !== null || !takeawayOrder.customer_slip_printed_at}
                >
                  {takeawayPrintBusy === "kitchen" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ChefHat className="h-4 w-4" />}
                  {!takeawayOrder.customer_slip_printed_at
                    ? "พิมพ์สลิปลูกค้าก่อน"
                    : takeawayOrder.kitchen_slip_printed_at
                      ? "พิมพ์ส่งครัวซ้ำ"
                      : "พิมพ์และส่งเข้า KDS"}
                </Button>
              </div>
              <p className="text-xs text-slate-500">ระบบจะสร้างงานใน KDS เมื่อกดพิมพ์และส่งเข้า KDS เพื่อป้องกันครัวทำรายการก่อนหน้าร้านยืนยันสลิปลูกค้า</p>
            </div>
          ) : null}
          <DialogFooter>
            <Button onClick={() => setTakeawayResultOpen(false)}>เริ่มออเดอร์ถัดไป</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <HoldDraftWorkspaceDialog
        open={heldBillsOpen}
        onOpenChange={setHeldBillsOpen}
        drafts={heldBills}
        isLoading={heldBillsQuery.isLoading}
        isError={heldBillsQuery.isError}
        isOnline={isOnline}
        canView={hasPermission("pos.draft.view")}
        canCreate={hasPermission("pos.draft.create") && Boolean(currentShift) && cart.items.length > 0}
        canResume={hasPermission("pos.draft.resume")}
        canDiscard={hasPermission("pos.draft.discard")}
        canReassign={hasPermission("pos.draft.reassign")}
        currentUserId={user?.id}
        branchId={branchId}
        hasCounter={Boolean(currentCounterDevice)}
        busyId={heldBillsBusy}
        search={heldBillsSearch}
        onSearchChange={setHeldBillsSearch}
        filter={heldBillsFilter}
        onFilterChange={setHeldBillsFilter}
        onRetry={() => void heldBillsQuery.refetch()}
        onCreate={() => { setHeldBillsOpen(false); setHoldCreateOpen(true); }}
        onResume={handleResumeHeldBill}
        onRelease={handleReleaseHeldBill}
        onDiscard={handleDeleteHeldBill}
        onReassign={handleReassignHeldBill}
        onReopen={handleReopenHeldBill}
      />

      <Dialog open={holdCreateOpen} onOpenChange={setHoldCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>พักบิลปัจจุบัน</DialogTitle>
            <DialogDescription>บันทึก Draft สำเร็จก่อนจึงล้างตะกร้า รายการนี้ยังไม่ส่งครัว ไม่ตัดสต๊อก ไม่สร้างภาษี และไม่รับชำระ</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Input className="h-14" placeholder="ชื่อบิล เช่น โต๊ะ 2 / ลูกค้ารอรับ" value={holdLabel} onChange={(event) => setHoldLabel(event.target.value)} autoFocus />
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 p-4"><div className="text-xs font-semibold text-slate-400">Context</div><div className="mt-1 font-bold">{currentCounterDevice?.device_code ?? "เครื่องนี้"} · {currentShift?.shift_number ?? "ยังไม่เปิดกะ"}</div><div className="text-sm text-slate-500">{currentLocationName} · {staffDisplayName}</div></div>
              <div className="rounded-2xl border border-slate-200 p-4"><div className="text-xs font-semibold text-slate-400">ยอดประมาณการ</div><div className="mt-1 text-2xl font-black">{formatThaiCurrency(finalTotal)}</div><div className="text-sm text-slate-500">{cart.items.reduce((sum, item) => sum + Number(item.qty), 0)} ชิ้น</div></div>
            </div>
            <div className={`rounded-2xl border p-4 text-sm ${isOnline ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
              {isOnline
                ? "บันทึกบน Server และเรียกต่อได้จาก Counter อื่นในสาขา"
                : isRetailMode
                  ? "Retail Offline: ปิดการพักบิลเพื่อป้องกันบิลซ้ำ กรุณาเชื่อมต่อ Server"
                  : "ออฟไลน์: เก็บ Local shadow เฉพาะเครื่องนี้ และต้องตรวจสอบหลังเชื่อมต่อ"}
            </div>
          </div>
          <DialogFooter>
            <Button className="h-12" variant="outline" onClick={() => setHoldCreateOpen(false)}>กลับ</Button>
            <Button className="h-14 min-w-52" onClick={() => void handleHoldBill()} disabled={cart.items.length === 0 || !currentShift || heldBillsBusy === "create"}>
              {heldBillsBusy === "create" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}พักบิล • ล้างตะกร้า
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(pendingResumeDraft)} onOpenChange={(open) => { if (!open) setPendingResumeDraft(null); }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>ตะกร้าปัจจุบันมีสินค้า</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm text-slate-600">
            <p>เลือกวิธีจัดการก่อนเรียก <strong>{pendingResumeDraft?.label}</strong> กลับมา ห้ามรวมรายการอัตโนมัติเพราะอาจทำให้สินค้าและส่วนลดซ้ำ</p>
            <Button
              className="h-16 w-full justify-start text-base"
              disabled={heldBillsBusy !== null}
              onClick={() => void (async () => {
                const target = pendingResumeDraft;
                if (!target) return;
                const held = await handleHoldBill();
                if (held) await resumeHeldBillNow(target);
              })()}
            >
              พักตะกร้าปัจจุบันก่อน แล้วเรียกบิล
            </Button>
            <Button
              className="h-16 w-full justify-start text-base"
              variant="destructive"
              disabled={heldBillsBusy !== null}
              onClick={() => void (async () => {
                const target = pendingResumeDraft;
                if (!target) return;
                const accepted = await confirm({
                  title: "แทนที่ตะกร้าปัจจุบัน",
                  description: `สินค้า ${cart.items.length} รายการในตะกร้าปัจจุบันจะถูกแทนที่`,
                  confirmLabel: "แทนที่ตะกร้า",
                  variant: "destructive",
                });
                if (accepted) await resumeHeldBillNow(target);
              })()}
            >
              แทนที่ตะกร้า
            </Button>
          </div>
          <DialogFooter>
            <Button className="h-14" variant="outline" onClick={() => setPendingResumeDraft(null)}>กลับ</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(pendingRevalidation)} onOpenChange={(open) => { if (!open) void rejectHeldRevalidation(); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>ตรวจความเปลี่ยนแปลงก่อนเรียกบิล</DialogTitle>
            <DialogDescription>Server ตรวจราคา ภาษี และจำนวนพร้อมขายใหม่แล้ว กรุณาเลือกยอมรับข้อมูลล่าสุดหรือกลับโดยไม่เปลี่ยนตะกร้า</DialogDescription>
          </DialogHeader>
          <div className="max-h-[55vh] space-y-3 overflow-y-auto">
            {(pendingRevalidation?.claim.price_changes ?? []).map((change, index) => {
              const kind = typeof change.kind === "string" ? change.kind : "price";
              return (
                <div key={`${kind}-${index}`} className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
                  {kind === "total" ? (
                    <><div className="font-bold">ยอดรวมเปลี่ยน</div><div className="mt-1">{formatThaiCurrency(Number(change.old_total ?? 0))} → {formatThaiCurrency(Number(change.new_total ?? 0))}</div></>
                  ) : kind === "availability" ? (
                    <><div className="font-bold">จำนวนพร้อมขายเปลี่ยน · {String(change.product_name ?? "สินค้า")}</div><div className="mt-1">ต้องการ {String(change.requested_qty ?? "-")} · พร้อมขาย {String(change.available_qty ?? "-")}</div></>
                  ) : (
                    <><div className="font-bold">ราคาเปลี่ยน · {String(change.product_name ?? "สินค้า")}</div><div className="mt-1">{formatThaiCurrency(Number(change.old_unit_price ?? 0))} → {formatThaiCurrency(Number(change.new_unit_price ?? 0))}</div></>
                  )}
                </div>
              );
            })}
          </div>
          <DialogFooter>
            <Button className="h-12" variant="outline" disabled={heldBillsBusy !== null} onClick={() => void rejectHeldRevalidation()}>ไม่ยอมรับ · ปล่อยบิลไว้</Button>
            <Button className="h-14" disabled={!pendingRevalidation || heldBillsBusy !== null} onClick={() => { if (pendingRevalidation) void finalizeHeldResume(pendingRevalidation.draft, pendingRevalidation.claim, true); }}>
              {heldBillsBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}ยอมรับข้อมูลล่าสุดและเรียกกลับ
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(holdConflict)} onOpenChange={(open) => { if (!open) setHoldConflict(null); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>บิลถูกเปลี่ยนจากอีกเครื่อง</DialogTitle>
            <DialogDescription>Server เป็นผู้ตัดสินผลล่าสุด ระบบไม่รวมข้อมูลและไม่เขียนทับอัตโนมัติ</DialogDescription>
          </DialogHeader>
          <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
            <div className="font-bold">{holdConflict?.message}</div>
            <div className="mt-2">สถานะล่าสุด: {holdConflict?.currentStatus ?? "ต้องโหลดใหม่"} · version {holdConflict?.currentVersion ?? "ล่าสุดบน Server"}</div>
            {holdConflict?.claimedBy ? <div className="mt-1">ผู้ถือสิทธิ์: {holdConflict.claimedBy}</div> : null}
          </div>
          <DialogFooter>
            <Button className="h-12" onClick={() => { setHoldConflict(null); void refreshHeldBills(); setHeldBillsOpen(true); }}>โหลดข้อมูลล่าสุด</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <BillReceiptCenterDialog
        open={recentSalesOpen}
        orders={recentSales}
        isLoading={recentSalesQuery.isLoading}
        isError={recentSalesQuery.isError}
        isRefreshing={recentSalesQuery.isFetching}
        updatedAt={recentSalesQuery.dataUpdatedAt}
        online={isOnline}
        canVoid={canVoidSale}
        canRefund={canRefundSale}
        onOpenChange={setRecentSalesOpen}
        onRetry={() => { void recentSalesQuery.refetch(); }}
        onPrint={(order) => {
          setLastOrder(order);
          setShowReceipt(true);
          setRecentSalesOpen(false);
        }}
        onVoid={(order) => {
          setVoidOrder(order);
          setVoidReason("");
          setRecentSalesOpen(false);
        }}
        onRefund={(order) => {
          setRefundWorkspaceOrder(order);
          setRecentSalesOpen(false);
        }}
      />

      <DiscountWorkspaceDialog
        open={discountWorkspaceOpen}
        subtotal={cart.subtotal}
        currentAmount={orderDiscount}
        enabled={!isTakeawayMode && discountAllowed}
        online={isOnline}
        canOverride={canOverrideDiscount}
        cashierLimitPct={cashierDiscountLimit}
        hardLimitPct={maxDiscountPct}
        onOpenChange={setDiscountWorkspaceOpen}
        onApply={handleOrderDiscountChange}
      />

      <Dialog open={priceEditorOpen} onOpenChange={setPriceEditorOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>แก้ราคาในบิล</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              type="number"
              value={priceEditValue}
              onChange={(event) => setPriceEditValue(event.target.value)}
              placeholder="ราคาใหม่"
            />
            <textarea
              className="min-h-20 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
              value={priceEditReason}
              onChange={(event) => setPriceEditReason(event.target.value)}
              placeholder="เหตุผลที่เปลี่ยนราคา (อย่างน้อย 3 ตัวอักษร)"
              maxLength={500}
            />
            <select
              className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
              value={priceEditReasonCode}
              onChange={(event) => setPriceEditReasonCode(event.target.value as typeof priceEditReasonCode)}
            >
              <option value="customer_recovery">ดูแลลูกค้า</option>
              <option value="price_match">เทียบราคาตลาด</option>
              <option value="manager_comp">ผู้จัดการให้ส่วนลด</option>
              <option value="damaged_item">สินค้ามีตำหนิ</option>
              <option value="manual_correction">แก้ราคาที่ตั้งผิด</option>
              <option value="other">อื่น ๆ</option>
            </select>
            <p className="text-sm text-slate-500">ใช้เฉพาะบิลนี้ และ Server จะบันทึกผู้ขอ ผู้อนุมัติ เหตุผล และราคาก่อน–หลัง</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPriceEditorOpen(false)}>ยกเลิก</Button>
            <Button onClick={handleApplyPriceOverride}>บันทึกราคาใหม่</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(voidOrder)} onOpenChange={(open) => { if (!open) { setVoidOrder(null); setVoidReason(""); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Void บิล</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="text-sm text-slate-600">
              {voidOrder ? `บิล ${voidOrder.order_number} • ${formatThaiCurrency(voidOrder.total_amount)}` : ""}
            </div>
            <textarea
              className="min-h-24 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
              placeholder="เหตุผลที่ต้อง void บิล"
              value={voidReason}
              onChange={(event) => setVoidReason(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setVoidOrder(null); setVoidReason(""); }}>ยกเลิก</Button>
            <Button onClick={() => void handleVoidSale()}>ยืนยัน void</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={scannerOpen} onOpenChange={setScannerOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>สแกนบาร์โค้ด / QR</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="overflow-hidden rounded-xl bg-slate-950">
              <video ref={scannerVideoRef} className="aspect-video w-full object-cover" muted playsInline />
            </div>
            <p className="text-sm text-slate-500">วางบาร์โค้ดหรือ QR ของสินค้าไว้กลางกล้อง ระบบจะเพิ่มสินค้าเข้าตะกร้าอัตโนมัติ</p>
            {scannerError ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{scannerError}</p> : null}
            {!cameraSupported ? <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">เบราว์เซอร์นี้ไม่อนุญาตให้เว็บไซต์เปิดกล้อง ให้ใช้การยิงบาร์โค้ดผ่านช่องค้นหาด้านบนแทน</p> : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setScannerOpen(false)}>ปิด</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CreateCustomerDialog
        open={createCustomerOpen}
        onOpenChange={setCreateCustomerOpen}
        requirePhone={loyaltySettingsQuery.data?.require_phone ?? true}
        onCreated={async (customerId) => {
          const response = await crmApi.getCustomer(customerId);
          const fullCustomer = response.data.data as Customer;
          setSelectedCustomer(fullCustomer);
          setCustomerName(fullCustomer.display_name || [fullCustomer.first_name, fullCustomer.last_name].filter(Boolean).join(" "));
          setCustomerPhone(fullCustomer.phone || "");
          setCustomerTaxId(fullCustomer.tax_id || "");
          setCustomerSearch("");
          setDebouncedCustomerSearch("");
        }}
      />
      <RedeemPointsDialog
        open={redeemOpen}
        onOpenChange={setRedeemOpen}
        customer={selectedCustomer}
        settings={loyaltySettingsQuery.data ?? null}
        onRedeemed={(discountAmount) => setLoyaltyDiscount(discountAmount)}
      />
      <RefundWorkspaceDialog
        open={Boolean(refundWorkspaceOrder)}
        order={refundWorkspaceOrder}
        shift={currentShift}
        online={isOnline}
        cashPilot={isRetailMode}
        onOpenChange={(next) => { if (!next) setRefundWorkspaceOrder(null); }}
        onCompleted={async () => {
          await recentSalesQuery.refetch();
        }}
      />
      {pendingManagerApproval ? (
        <ManagerApprovalDialog
          open
          onOpenChange={(open) => {
            if (!open) setPendingManagerApproval(null);
          }}
          action={pendingManagerApproval.action}
          requestPayload={pendingManagerApproval.requestPayload}
          reason={pendingManagerApproval.reason}
          description={pendingManagerApproval.description}
          onApproved={pendingManagerApproval.onApproved}
        />
      ) : null}
      <div className="fixed -left-[9999px] top-0">
        <div ref={takeawayCustomerSlipRef} className="wap-print-slip">
          <TakeawayOrderSlip
            order={takeawayOrder}
            type="customer"
            employeeName={staffDisplayName}
            menu={takeawayMenuQuery.data ?? null}
            promptpayQrDataUrl={takeawayOrder?.payment_method === "promptpay" ? qrDataUrl : null}
          />
        </div>
        <div ref={takeawayKitchenSlipRef} className="wap-print-slip">
          <TakeawayOrderSlip
            order={takeawayOrder}
            type="kitchen"
            employeeName={staffDisplayName}
            menu={takeawayMenuQuery.data ?? null}
          />
        </div>
      </div>
    </div>
  );
}
