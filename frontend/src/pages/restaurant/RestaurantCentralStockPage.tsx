import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ClipboardCheck, History, ImagePlus, Loader2, PackagePlus, Pencil, Plus, Search, Settings, Trash2, Warehouse, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authApi } from "@/lib/api";
import { categoryApi, productApi, unitApi } from "@/lib/productApi";
import { stockCountApi } from "@/lib/stockCountApi";
import { stockApi } from "@/lib/stockApi";
import type { Category, Product, ProductListItem, Unit } from "@/types/product";
import type { StockBalance, StockMovement } from "@/types/stock";

type StockFilter = "all" | "low" | "zero";
type StockArea = "storefront" | "backoffice" | "production";
type StockAreaLocation = {
  branch_id: string | null;
  branch_code: string | null;
  branch_name: string | null;
  location_id: string | null;
  location_code: string | null;
  location_name: string | null;
  is_configured: boolean;
};
type StockAreasResponse = {
  production: StockAreaLocation;
  backoffice: StockAreaLocation;
  storefronts: StockAreaLocation[];
  is_separated: boolean;
};
type StockRow = {
  product: ProductListItem;
  balance?: StockBalance;
  category: Category | null;
  qtyOnHand: number;
  qtyReserved: number;
  qtyAvailable: number;
  minQty: number;
  unitCode: string | null;
  costPerUnit: number;
};
type IngredientFormState = {
  id: string | null;
  sku: string;
  name: string;
  category_id: string;
  unit_id: string;
  cost_price: string;
  min_stock_qty: string;
  image_url: string | null;
  image_file: File | null;
};
type CategoryFormState = { id: string | null; name: string; code: string };
type UnitFormState = { id: string | null; code: string; name: string; decimal_places: string };
const UNCATEGORIZED = "__uncategorized";

const EMPTY_INGREDIENT_FORM: IngredientFormState = {
  id: null,
  sku: "",
  name: "",
  category_id: "",
  unit_id: "",
  cost_price: "",
  min_stock_qty: "",
  image_url: null,
  image_file: null,
};
const EMPTY_CATEGORY_FORM: CategoryFormState = { id: null, name: "", code: "" };
const EMPTY_UNIT_FORM: UnitFormState = { id: null, code: "", name: "", decimal_places: "0" };

function centralBasePath(brandSlug?: string): string {
  return brandSlug ? `/central/${brandSlug}` : "/restaurant";
}

function centralApiPath(brandSlug?: string): string {
  return brandSlug ? `/restaurant/central/${brandSlug}` : "/restaurant";
}

function formatQty(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString("th-TH")
    : value.toLocaleString("th-TH", { maximumFractionDigits: 3 });
}

function formatMoney(value: number): string {
  return value.toLocaleString("th-TH", { style: "currency", currency: "THB", maximumFractionDigits: 2 });
}

function stockStatus(qty: number, minQty: number): { label: string; className: string } {
  if (qty <= 0) return { label: "หมด", className: "bg-rose-100 text-rose-700" };
  if (minQty > 0 && qty <= minQty) return { label: "ต่ำกว่าจุดสั่ง", className: "bg-amber-100 text-amber-700" };
  return { label: "พอใช้", className: "bg-emerald-100 text-emerald-700" };
}

export default function RestaurantCentralStockPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const centralBase = centralBasePath(brandSlug);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<StockFilter>("all");
  const [stockArea, setStockArea] = useState<StockArea>("production");
  const [storeBranchId, setStoreBranchId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [receiveProductId, setReceiveProductId] = useState("");
  const [receiveQty, setReceiveQty] = useState("");
  const [receiveCost, setReceiveCost] = useState("");
  const [receiveNote, setReceiveNote] = useState("รับวัตถุดิบเข้าคลัง RAW");
  const [ingredientModalOpen, setIngredientModalOpen] = useState(false);
  const [ingredientForm, setIngredientForm] = useState<IngredientFormState>(EMPTY_INGREDIENT_FORM);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [categoryForm, setCategoryForm] = useState<CategoryFormState>(EMPTY_CATEGORY_FORM);
  const [unitForm, setUnitForm] = useState<UnitFormState>(EMPTY_UNIT_FORM);
  const [historyProduct, setHistoryProduct] = useState<StockRow | null>(null);
  const rawMaterialsQueryKey = ["restaurant-central-raw-materials", brandSlug ?? "_unbranded"] as const;

  const stockAreasQuery = useQuery({
    queryKey: ["restaurant-central-stock-areas", brandSlug ?? "_unbranded"],
    queryFn: async () => (
      await authApi.get(`${centralApiPath(brandSlug)}/stock-areas`)
    ).data.data as StockAreasResponse,
  });
  useEffect(() => {
    if (!storeBranchId && stockAreasQuery.data?.storefronts.length) {
      setStoreBranchId(stockAreasQuery.data.storefronts[0].branch_id ?? "");
    }
  }, [stockAreasQuery.data?.storefronts, storeBranchId]);
  const selectedStorefront = stockAreasQuery.data?.storefronts.find(
    (item) => item.branch_id === storeBranchId,
  ) ?? null;
  const activeAreaConfig = stockArea === "production"
    ? stockAreasQuery.data?.production
    : stockArea === "backoffice"
      ? stockAreasQuery.data?.backoffice
      : selectedStorefront;
  const activeLocationId = activeAreaConfig?.location_id ?? null;
  const activeInventoryRole = stockArea === "production"
    ? "central_raw"
    : stockArea === "backoffice"
      ? "central_ready"
      : "store_local";
  const activeStockLabel = stockArea === "production"
    ? "ฝ่ายผลิต"
    : stockArea === "backoffice"
      ? "หลังบ้าน"
      : "หน้าร้าน";
  const canManageStock = stockArea !== "storefront";

  const rawMaterialsQuery = useQuery({
    queryKey: rawMaterialsQueryKey,
    queryFn: async () => {
      const response = await authApi.get(`${centralApiPath(brandSlug)}/recipe-products`);
      return response.data.data as ProductListItem[];
    },
  });

  const categoriesQuery = useQuery({
    queryKey: ["restaurant-central-stock-categories"],
    queryFn: async () => {
      try {
        const response = await authApi.get("/categories");
        return response.data.data as Category[];
      } catch {
        return [];
      }
    },
  });

  const unitsQuery = useQuery({
    queryKey: ["restaurant-central-stock-units"],
    queryFn: async () => {
      const response = await unitApi.list();
      return response.data.data as Unit[];
    },
  });

  const balancesQuery = useQuery({
    queryKey: ["restaurant-central-stock", brandSlug ?? "_unbranded", stockArea, storeBranchId, activeLocationId],
    queryFn: async () => (
      await authApi.get(`${centralApiPath(brandSlug)}/stock-balances`, {
        params: {
          area: stockArea,
          branch_id: stockArea === "storefront" ? storeBranchId : undefined,
        },
      })
    ).data.data as StockBalance[],
    enabled: Boolean(activeLocationId),
  });

  const movementsQuery = useQuery({
    queryKey: ["restaurant-central-stock-movements", stockArea, storeBranchId, activeLocationId, historyProduct?.product.id],
    queryFn: async () => {
      const response = await authApi.get(`${centralApiPath(brandSlug)}/stock-movements`, {
        params: {
          area: stockArea,
          branch_id: stockArea === "storefront" ? storeBranchId : undefined,
          product_id: historyProduct?.product.id,
          limit: 30,
        },
      });
      return response.data.data as StockMovement[];
    },
    enabled: Boolean(historyProduct && activeLocationId),
  });

  const rows = useMemo(() => {
    const balanceByProduct = new Map((balancesQuery.data ?? []).map((balance) => [balance.product_id, balance]));
    const categoryById = new Map((categoriesQuery.data ?? []).map((category) => [category.id, category]));
    return (rawMaterialsQuery.data ?? [])
      .filter((product) => {
        const roleMatches = stockArea === "production"
          ? product.inventory_role === "central_raw"
          : stockArea === "backoffice"
            ? product.inventory_role === "central_ready"
            : product.inventory_role === "central_ready" || product.inventory_role === "store_local";
        return roleMatches || balanceByProduct.has(product.id);
      })
      .map((product): StockRow => {
      const balance = balanceByProduct.get(product.id);
      const category = product.category_id ? categoryById.get(product.category_id) ?? null : null;
      const qtyOnHand = Number(balance?.qty_on_hand ?? 0);
      const qtyReserved = Number(balance?.qty_reserved ?? 0);
      const qtyAvailable = Number(balance?.qty_available ?? 0);
      const minQty = Number(product.min_stock_qty ?? balance?.min_stock_qty ?? 0);
      const unitCode = product.unit?.code ?? balance?.unit_code ?? null;
      const costPerUnit = Number(balance?.cost_per_unit ?? product.cost_price ?? 0);
      return { product, balance, category, qtyOnHand, qtyReserved, qtyAvailable, minQty, unitCode, costPerUnit };
      });
  }, [balancesQuery.data, categoriesQuery.data, rawMaterialsQuery.data, stockArea]);

  const categoryOptions = useMemo(() => {
    const options = new Map<string, { id: string; name: string; count: number }>();
    for (const row of rows) {
      const id = row.product.category_id ?? UNCATEGORIZED;
      const name = row.category?.name ?? "ไม่มีหมวดหมู่";
      const current = options.get(id);
      if (current) {
        current.count += 1;
      } else {
        options.set(id, { id, name, count: 1 });
      }
    }
    return Array.from(options.values()).sort((a, b) => a.name.localeCompare(b.name, "th"));
  }, [rows]);

  const filteredRows = rows.filter((row) => {
    const rowCategoryId = row.product.category_id ?? UNCATEGORIZED;
    if (categoryId && rowCategoryId !== categoryId) return false;
    const haystack = `${row.product.name} ${row.product.sku} ${row.category?.name ?? ""}`.toLowerCase();
    if (search.trim() && !haystack.includes(search.trim().toLowerCase())) return false;
    if (filter === "zero") return row.qtyOnHand <= 0;
    if (filter === "low") return row.minQty > 0 && row.qtyOnHand <= row.minQty;
    return true;
  });

  const lowCount = rows.filter((row) => row.minQty > 0 && row.qtyOnHand <= row.minQty && row.qtyOnHand > 0).length;
  const zeroCount = rows.filter((row) => row.qtyOnHand <= 0).length;
  const totalValue = rows.reduce((sum, row) => sum + row.qtyOnHand * row.costPerUnit, 0);
  const categoryCount = categoryOptions.length;

  const receiveMutation = useMutation({
    mutationFn: async () => {
      if (!activeLocationId || !receiveProductId) return;
      await stockApi.receive({
        location_id: activeLocationId,
        items: [{
          product_id: receiveProductId,
          qty: Number(receiveQty || 0),
          cost_per_unit: receiveCost ? Number(receiveCost) : undefined,
        }],
        note: receiveNote || `รับสินค้าเข้าคลัง ${activeStockLabel}`,
        reference_type: stockArea === "production" ? "central_raw_material_receive" : "central_ready_receive",
      });
    },
    onSuccess: async () => {
      setReceiveProductId("");
      setReceiveQty("");
      setReceiveCost("");
      await queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock"] });
      window.alert(`รับสินค้าเข้าคลัง ${activeStockLabel} แล้ว`);
    },
    onError: () => window.alert(`รับสินค้าเข้า ${activeStockLabel} ไม่สำเร็จ กรุณาตรวจจำนวนหรือสิทธิ์ผู้ใช้`),
  });

  const ingredientMutation = useMutation({
    mutationFn: async () => {
      const payload: Partial<Product> = {
        sku: ingredientForm.sku.trim(),
        name: ingredientForm.name.trim(),
        product_type: "raw_material",
        inventory_role: activeInventoryRole,
        cost_price: Number(ingredientForm.cost_price || 0),
        selling_price: 0,
        vat_type: "included",
        vat_rate: 7,
        category_id: ingredientForm.category_id || null,
        unit_id: ingredientForm.unit_id || null,
        min_stock_qty: Number(ingredientForm.min_stock_qty || 0),
        is_active: true,
        is_for_sale: false,
        is_for_purchase: true,
      };
      const response = ingredientForm.id
        ? await productApi.update(ingredientForm.id, payload)
        : await productApi.create(payload);
      const productId = response.data.data.id as string;
      if (ingredientForm.image_file) {
        await productApi.uploadImage(productId, ingredientForm.image_file, true);
      }
    },
    onSuccess: async () => {
      setIngredientModalOpen(false);
      setIngredientForm(EMPTY_INGREDIENT_FORM);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: rawMaterialsQueryKey }),
        queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock"] }),
      ]);
      window.alert("บันทึกวัตถุดิบแล้ว");
    },
    onError: () => window.alert("บันทึกวัตถุดิบไม่สำเร็จ กรุณาตรวจ SKU ซ้ำหรือสิทธิ์ผู้ใช้"),
  });

  const inlineCategoryMutation = useMutation({
    mutationFn: async ({ productId, categoryId }: { productId: string; categoryId: string | null }) => {
      await productApi.update(productId, { category_id: categoryId });
    },
    onMutate: async ({ productId, categoryId }) => {
      await queryClient.cancelQueries({ queryKey: rawMaterialsQueryKey });
      const previousProducts = queryClient.getQueryData<ProductListItem[]>(rawMaterialsQueryKey);
      queryClient.setQueryData<ProductListItem[]>(rawMaterialsQueryKey, (products) => (
        products?.map((product) => (
          product.id === productId ? { ...product, category_id: categoryId } : product
        ))
      ));
      return { previousProducts };
    },
    onError: (_error, _variables, context) => {
      if (context?.previousProducts) {
        queryClient.setQueryData(rawMaterialsQueryKey, context.previousProducts);
      }
      window.alert("เปลี่ยนหมวดหมู่ไม่สำเร็จ กรุณาตรวจสิทธิ์ผู้ใช้แล้วลองใหม่");
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: rawMaterialsQueryKey });
    },
  });

  const categoryMutation = useMutation({
    mutationFn: async () => {
      const trimmedCode = categoryForm.code.trim();
      const trimmedName = categoryForm.name.trim();
      const existing = (categoriesQuery.data ?? []).find((category) => {
        if (categoryForm.id && category.id === categoryForm.id) return false;
        const codeMatches = trimmedCode && (category.code ?? "").toLowerCase() === trimmedCode.toLowerCase();
        const nameMatches = category.name.trim().toLowerCase() === trimmedName.toLowerCase();
        return codeMatches || nameMatches;
      });
      const payload = {
        name: trimmedName,
        code: trimmedCode || null,
        is_active: true,
      };
      if (categoryForm.id || existing) {
        await categoryApi.update(categoryForm.id || existing!.id, payload);
      } else {
        await categoryApi.create(payload);
      }
    },
    onSuccess: async () => {
      setCategoryForm(EMPTY_CATEGORY_FORM);
      await queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock-categories"] });
      window.alert("บันทึกหมวดหมู่แล้ว");
    },
    onError: () => window.alert("บันทึกหมวดหมู่ไม่สำเร็จ กรุณาตรวจรหัสซ้ำหรือสิทธิ์ผู้ใช้"),
  });

  const unitMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        code: unitForm.code.trim(),
        name: unitForm.name.trim(),
        decimal_places: Number(unitForm.decimal_places || 0),
        is_active: true,
      };
      if (unitForm.id) {
        await unitApi.update(unitForm.id, payload);
      } else {
        await unitApi.create(payload);
      }
    },
    onSuccess: async () => {
      setUnitForm(EMPTY_UNIT_FORM);
      await queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock-units"] });
      window.alert("บันทึกหน่วยแล้ว");
    },
    onError: () => window.alert("บันทึกหน่วยไม่สำเร็จ กรุณาตรวจรหัสซ้ำหรือสิทธิ์ผู้ใช้"),
  });

  const deleteCategoryMutation = useMutation({
    mutationFn: (category: Category) => categoryApi.delete(category.id),
    onSuccess: async (_, category) => {
      if (categoryForm.id === category.id) setCategoryForm(EMPTY_CATEGORY_FORM);
      await queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock-categories"] });
      window.alert("ลบหมวดหมู่แล้ว");
    },
    onError: () => window.alert("ลบหมวดหมู่ไม่ได้ หมวดหมู่นี้อาจยังมีสินค้าใช้งานอยู่ หรือคุณไม่มีสิทธิ์ลบ"),
  });

  const deleteUnitMutation = useMutation({
    mutationFn: (unit: Unit) => unitApi.delete(unit.id),
    onSuccess: async (_, unit) => {
      if (unitForm.id === unit.id) setUnitForm(EMPTY_UNIT_FORM);
      await queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock-units"] });
      window.alert("ลบหน่วยนับแล้ว");
    },
    onError: () => window.alert("ลบหน่วยนับไม่ได้ หน่วยนี้อาจยังถูกใช้งานอยู่ หรือคุณไม่มีสิทธิ์ลบ"),
  });

  const confirmDeleteCategory = (category: Category) => {
    if (window.confirm(`ยืนยันลบหมวดหมู่ “${category.name}” หรือไม่?`)) {
      deleteCategoryMutation.mutate(category);
    }
  };

  const confirmDeleteUnit = (unit: Unit) => {
    if (window.confirm(`ยืนยันลบหน่วยนับ “${unit.name}” หรือไม่?`)) {
      deleteUnitMutation.mutate(unit);
    }
  };

  const stockCountMutation = useMutation({
    mutationFn: async () => {
      if (!activeLocationId || !activeAreaConfig?.branch_id) return null;
      const response = await stockCountApi.createSession({
        branch_id: activeAreaConfig.branch_id,
        location_id: activeLocationId,
        count_date: new Date().toISOString().slice(0, 10),
        note: `นับสต็อกคลังกลาง ${activeStockLabel}`,
        product_ids: rows.map((row) => row.product.id),
      });
      return response.data.data as { id: string };
    },
    onSuccess: (session) => {
      if (session?.id) {
        navigate(`/stock-count/${session.id}`);
      }
    },
    onError: () => window.alert("เริ่มนับสต็อกไม่สำเร็จ กรุณาตรวจคลังกลางหรือสิทธิ์ผู้ใช้"),
  });

  function prefillReceive(productId: string, qty = 1, cost = 0): void {
    setReceiveProductId(productId);
    setReceiveQty(String(qty > 0 ? qty : 1));
    setReceiveCost(cost > 0 ? String(cost) : "");
  }

  function openCreateIngredient(): void {
    setIngredientForm(EMPTY_INGREDIENT_FORM);
    setIngredientModalOpen(true);
  }

  function openEditIngredient(row: StockRow): void {
    setIngredientForm({
      id: row.product.id,
      sku: row.product.sku,
      name: row.product.name,
      category_id: row.product.category_id ?? "",
      unit_id: row.product.unit_id ?? "",
      cost_price: String(row.product.cost_price ?? row.costPerUnit ?? ""),
      min_stock_qty: String(row.product.min_stock_qty ?? row.minQty ?? ""),
      image_url: row.product.image_url,
      image_file: null,
    });
    setIngredientModalOpen(true);
  }

  const isLoading = stockAreasQuery.isLoading || rawMaterialsQuery.isLoading || balancesQuery.isLoading || categoriesQuery.isLoading || unitsQuery.isLoading;
  const isError = stockAreasQuery.isError || rawMaterialsQuery.isError || balancesQuery.isError;

  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col gap-4">
      <header className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <Button asChild variant="outline" size="icon" className="h-10 w-10 shrink-0">
              <Link to={`${centralBase}/production`} aria-label="กลับหน้า Production">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-black text-slate-950">จัดการสต็อก {brandSlug || "ร้านอาหาร"}</h1>
              <p className="truncate text-sm text-slate-500">
                {activeStockLabel}
                {activeAreaConfig?.location_name ? ` · ${activeAreaConfig.location_name}` : ""}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setSettingsModalOpen(true)}>
              <Settings className="mr-2 h-4 w-4" />
              ตั้งค่า
            </Button>
            {canManageStock ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!activeLocationId || rows.length === 0 || stockCountMutation.isPending}
                  onClick={() => stockCountMutation.mutate()}
                >
                  <ClipboardCheck className="mr-2 h-4 w-4" />
                  {stockCountMutation.isPending ? "กำลังสร้าง..." : "นับสต็อก"}
                </Button>
                <Button type="button" className="bg-blue-600 hover:bg-blue-700" size="sm" onClick={openCreateIngredient}>
                  <Plus className="mr-2 h-4 w-4" />
                  เพิ่มสินค้า {activeStockLabel}
                </Button>
              </>
            ) : null}
            <Button asChild variant="outline" size="sm">
              <Link to={`${centralBase}/production`}>Production</Link>
            </Button>
          </div>
        </div>
      </header>

      <section className="rounded-lg border border-slate-200 bg-white p-3">
        <p className="mb-2 text-xs font-black uppercase tracking-wide text-slate-500">พื้นที่สต็อก</p>
        <div className="grid grid-cols-3 gap-1 rounded-md bg-slate-100 p-1">
        {([
          ["storefront", "หน้าร้าน"],
          ["backoffice", "หลังบ้าน"],
          ["production", "ฝ่ายผลิต"],
        ] as Array<[StockArea, string]>).map(([area, label]) => {
          const selected = stockArea === area;
          return (
            <button
              key={area}
              type="button"
              className={`rounded-md px-4 py-2 text-sm font-bold ${selected ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-slate-100"}`}
              onClick={() => {
                setStockArea(area);
                setReceiveProductId("");
                setReceiveQty("");
                setReceiveCost("");
                setReceiveNote(
                  area === "production"
                    ? "รับวัตถุดิบเข้าฝ่ายผลิต"
                    : area === "backoffice"
                      ? "รับสินค้าพร้อมส่งเข้าหลังบ้าน"
                      : "",
                );
                setHistoryProduct(null);
              }}
            >
              {label}
            </button>
          );
        })}
        </div>
        {stockArea === "storefront" ? (
          <div className="mt-3">
            <label className="mb-1 block text-xs font-bold text-slate-500">เลือกสาขาหน้าร้าน</label>
            <select
              className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm sm:max-w-sm"
              value={storeBranchId}
              onChange={(event) => {
                setStoreBranchId(event.target.value);
                setHistoryProduct(null);
              }}
            >
              {stockAreasQuery.data?.storefronts.map((item) => (
                <option key={item.branch_id} value={item.branch_id ?? ""}>
                  {item.branch_name ?? item.branch_code ?? "ไม่ทราบสาขา"}
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </section>

      {stockAreasQuery.data && !stockAreasQuery.data.is_separated ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p className="font-black">ฐานข้อมูลยังไม่แยกสต็อกครบ 3 พื้นที่</p>
          <p className="mt-1">
            กรุณาตั้งคลังฝ่ายผลิต หลังบ้าน และหน้าร้านให้เป็นคนละ location แล้วทำ Stock Cutover ก่อนใช้งานจริง
          </p>
          <Button asChild variant="outline" size="sm" className="mt-3 border-amber-300 bg-white">
            <Link to={`${centralBase}/cutover`}>ไปหน้าตรวจ Cutover</Link>
          </Button>
        </section>
      ) : null}

      {isLoading ? (
        <div className="flex h-72 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          โหลดคลัง {activeStockLabel}
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-center font-semibold text-rose-700">
          โหลดคลัง {activeStockLabel} ไม่สำเร็จ
        </div>
      ) : (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">สินค้า {activeStockLabel} ทั้งหมด</p>
              <p className="mt-2 text-3xl font-black text-slate-950">{rows.length}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">หมวดหมู่</p>
              <p className="mt-2 text-3xl font-black text-blue-700">{categoryCount}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">ใกล้หมด</p>
              <p className="mt-2 text-3xl font-black text-amber-700">{lowCount}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">หมด</p>
              <p className="mt-2 text-3xl font-black text-rose-700">{zeroCount}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-500">มูลค่าคงเหลือ</p>
              <p className="mt-2 text-2xl font-black text-emerald-700">{formatMoney(totalValue)}</p>
            </div>
          </section>

          {!activeLocationId ? (
            <section className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
              ยังไม่ได้ตั้งคลัง {activeStockLabel} ของแบรนด์ จึงยังแสดงยอดคงเหลือไม่ได้
            </section>
          ) : null}

          {canManageStock ? (
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="mb-3 flex items-center gap-2">
              <PackagePlus className="h-5 w-5 text-blue-700" />
              <h2 className="font-bold text-slate-950">รับสินค้าเข้าคลัง {activeStockLabel}</h2>
            </div>
            <div className="grid gap-3 lg:grid-cols-[1fr_130px_130px_1fr_auto]">
              <select
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                value={receiveProductId}
                disabled={!activeLocationId}
                onChange={(event) => {
                  const product = rows.find((row) => row.product.id === event.target.value);
                  setReceiveProductId(event.target.value);
                  setReceiveCost(product && product.costPerUnit > 0 ? String(product.costPerUnit) : "");
                }}
              >
                <option value="">เลือกสินค้า {activeStockLabel}</option>
                {rows.map((row) => (
                  <option key={row.product.id} value={row.product.id}>
                    {row.product.name} ({row.product.sku})
                    {row.category?.name ? ` - ${row.category.name}` : ""}
                  </option>
                ))}
              </select>
              <Input
                type="number"
                min="0.001"
                step="0.001"
                value={receiveQty}
                disabled={!activeLocationId}
                onChange={(event) => setReceiveQty(event.target.value)}
                placeholder="จำนวน"
              />
              <Input
                type="number"
                min="0"
                step="0.0001"
                value={receiveCost}
                disabled={!activeLocationId}
                onChange={(event) => setReceiveCost(event.target.value)}
                placeholder="ทุน/หน่วย"
              />
              <Input
                value={receiveNote}
                disabled={!activeLocationId}
                onChange={(event) => setReceiveNote(event.target.value)}
                placeholder="หมายเหตุ"
              />
              <Button
                className="bg-blue-600 hover:bg-blue-700"
                disabled={!activeLocationId || !receiveProductId || Number(receiveQty || 0) <= 0 || receiveMutation.isPending}
                onClick={() => receiveMutation.mutate()}
              >
                {receiveMutation.isPending ? "กำลังรับ..." : "รับเข้า"}
              </Button>
            </div>
          </section>
          ) : (
            <section className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
              มุมมองหน้าร้านในหลังบ้านเป็นแบบอ่านอย่างเดียว การรับสินค้าเข้าร้านต้องยืนยันจากหน้าร้าน
              เพื่อให้ยอดระหว่างทางและผู้รับสินค้าถูกบันทึกครบถ้วน
            </section>
          )}

          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="grid gap-3 border-b border-slate-200 p-4 lg:grid-cols-[1fr_220px_auto] lg:items-center">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  className="pl-9"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="ค้นหาชื่อวัตถุดิบหรือ SKU"
                />
              </div>
              <select
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
              >
                <option value="">ทุกหมวดหมู่</option>
                {categoryOptions.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name} ({category.count})
                  </option>
                ))}
              </select>
              <div className="grid grid-cols-3 rounded-md border border-slate-200 p-1 text-sm font-semibold">
                {[
                  ["all", "ทั้งหมด"],
                  ["low", "ใกล้หมด"],
                  ["zero", "หมด"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={`rounded px-3 py-1.5 ${filter === value ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-slate-100"}`}
                    onClick={() => setFilter(value as StockFilter)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs font-bold uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">วัตถุดิบ</th>
                    <th className="px-4 py-3">หมวดหมู่</th>
                    <th className="px-4 py-3 text-right">คงเหลือ</th>
                    <th className="px-4 py-3 text-right">จองไว้</th>
                    <th className="px-4 py-3 text-right">ใช้ได้</th>
                    <th className="px-4 py-3 text-right">จุดสั่งเพิ่ม</th>
                    <th className="px-4 py-3 text-right">ทุน/หน่วย</th>
                    <th className="px-4 py-3 text-right">สถานะ</th>
                    <th className="px-4 py-3 text-right">จัดการ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredRows.length > 0 ? filteredRows.map((row) => {
                    const status = stockStatus(row.qtyOnHand, row.minQty);
                    const unit = row.unitCode ?? "";
                    return (
                      <tr key={row.product.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md border border-slate-200 bg-slate-50">
                              {row.product.image_url ? (
                                <img src={row.product.image_url} alt={row.product.name} className="h-full w-full object-cover" />
                              ) : (
                                <Warehouse className="h-5 w-5 text-slate-400" />
                              )}
                            </div>
                            <div className="min-w-0">
                              <p className="font-bold text-slate-950">{row.product.name}</p>
                              <p className="text-xs text-slate-500">{row.product.sku}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex min-w-44 items-center gap-2">
                            <select
                              aria-label={`เปลี่ยนหมวดหมู่ ${row.product.name}`}
                              className="h-9 min-w-0 flex-1 cursor-pointer rounded-md border border-blue-200 bg-blue-50 px-2 text-xs font-bold text-blue-700 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
                              value={row.product.category_id ?? ""}
                              disabled={!canManageStock || inlineCategoryMutation.isPending}
                              onChange={(event) => {
                                const nextCategoryId = event.target.value || null;
                                if (nextCategoryId !== row.product.category_id) {
                                  inlineCategoryMutation.mutate({
                                    productId: row.product.id,
                                    categoryId: nextCategoryId,
                                  });
                                }
                              }}
                            >
                              <option value="">ไม่มีหมวดหมู่</option>
                              {(categoriesQuery.data ?? []).map((category) => (
                                <option key={category.id} value={category.id}>
                                  {category.name}
                                </option>
                              ))}
                            </select>
                            {inlineCategoryMutation.isPending
                            && inlineCategoryMutation.variables?.productId === row.product.id ? (
                              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-600" />
                            ) : null}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right font-bold text-slate-950">{formatQty(row.qtyOnHand)} {unit}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{formatQty(row.qtyReserved)} {unit}</td>
                        <td className="px-4 py-3 text-right font-semibold text-emerald-700">{formatQty(row.qtyAvailable)} {unit}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{formatQty(row.minQty)} {unit}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{formatMoney(row.costPerUnit)}</td>
                        <td className="px-4 py-3 text-right">
                          <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-bold ${status.className}`}>{status.label}</span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex justify-end gap-2">
                            {canManageStock ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => openEditIngredient(row)}
                              >
                                <Pencil className="mr-1 h-3.5 w-3.5" />
                                แก้ไข
                              </Button>
                            ) : null}
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => setHistoryProduct(row)}
                            >
                              <History className="mr-1 h-3.5 w-3.5" />
                              ประวัติ
                            </Button>
                          {canManageStock ? (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={!activeLocationId}
                              onClick={() => prefillReceive(row.product.id, row.minQty > row.qtyOnHand ? row.minQty - row.qtyOnHand : 1, row.costPerUnit)}
                            >
                              รับเข้า
                            </Button>
                          ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  }) : (
                    <tr>
                      <td colSpan={9} className="px-4 py-10 text-center text-slate-500">ไม่พบวัตถุดิบตามเงื่อนไข</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {ingredientModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="max-h-[92vh] w-full max-w-2xl overflow-auto rounded-lg bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-lg font-black text-slate-950">
                  {ingredientForm.id ? `แก้ไขสินค้า ${activeStockLabel}` : `เพิ่มสินค้า ${activeStockLabel}`}
                </h2>
                <p className="text-sm text-slate-500">ข้อมูลนี้ใช้ร่วมกับสูตรและ stock กลางของ Restaurant</p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-9 w-9"
                onClick={() => {
                  setIngredientModalOpen(false);
                  setIngredientForm(EMPTY_INGREDIENT_FORM);
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="grid gap-4 p-5 sm:grid-cols-2">
              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                SKU
                <Input
                  value={ingredientForm.sku}
                  onChange={(event) => setIngredientForm((prev) => ({ ...prev, sku: event.target.value }))}
                  placeholder="เช่น MENU-001"
                />
              </label>
              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                ชื่อวัตถุดิบ
                <Input
                  value={ingredientForm.name}
                  onChange={(event) => setIngredientForm((prev) => ({ ...prev, name: event.target.value }))}
                  placeholder="ชื่อวัตถุดิบ"
                />
              </label>
              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                หมวดหมู่
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={ingredientForm.category_id}
                  onChange={(event) => setIngredientForm((prev) => ({ ...prev, category_id: event.target.value }))}
                >
                  <option value="">ไม่มีหมวดหมู่</option>
                  {(categoriesQuery.data ?? []).map((category) => (
                    <option key={category.id} value={category.id}>{category.name}</option>
                  ))}
                </select>
              </label>
              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                หน่วย
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={ingredientForm.unit_id}
                  onChange={(event) => setIngredientForm((prev) => ({ ...prev, unit_id: event.target.value }))}
                >
                  <option value="">ไม่ระบุหน่วย</option>
                  {(unitsQuery.data ?? []).map((unit) => (
                    <option key={unit.id} value={unit.id}>{unit.name} ({unit.code})</option>
                  ))}
                </select>
              </label>
              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                ราคาทุน/หน่วย
                <Input
                  type="number"
                  min="0"
                  step="0.0001"
                  value={ingredientForm.cost_price}
                  onChange={(event) => setIngredientForm((prev) => ({ ...prev, cost_price: event.target.value }))}
                  placeholder="0.00"
                />
              </label>
              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                จุดสั่งเพิ่ม
                <Input
                  type="number"
                  min="0"
                  step="0.001"
                  value={ingredientForm.min_stock_qty}
                  onChange={(event) => setIngredientForm((prev) => ({ ...prev, min_stock_qty: event.target.value }))}
                  placeholder="0"
                />
              </label>
              <label className="grid gap-2 text-sm font-semibold text-slate-700 sm:col-span-2">
                รูปวัตถุดิบ
                <div className="grid gap-3 sm:grid-cols-[96px_1fr] sm:items-center">
                  <div className="flex h-24 w-24 items-center justify-center overflow-hidden rounded-md border border-slate-200 bg-slate-50">
                    {ingredientForm.image_url ? (
                      <img src={ingredientForm.image_url} alt={ingredientForm.name || "วัตถุดิบ"} className="h-full w-full object-cover" />
                    ) : (
                      <ImagePlus className="h-6 w-6 text-slate-400" />
                    )}
                  </div>
                  <div>
                    <Input
                      type="file"
                      accept="image/*"
                      onChange={(event) => setIngredientForm((prev) => ({ ...prev, image_file: event.target.files?.[0] ?? null }))}
                    />
                    {ingredientForm.image_file ? (
                      <p className="mt-1 text-xs text-slate-500">{ingredientForm.image_file.name}</p>
                    ) : null}
                  </div>
                </div>
              </label>
            </div>

            <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setIngredientModalOpen(false);
                  setIngredientForm(EMPTY_INGREDIENT_FORM);
                }}
              >
                ยกเลิก
              </Button>
              <Button
                type="button"
                className="bg-blue-600 hover:bg-blue-700"
                disabled={!ingredientForm.sku.trim() || !ingredientForm.name.trim() || ingredientMutation.isPending}
                onClick={() => ingredientMutation.mutate()}
              >
                {ingredientMutation.isPending ? "กำลังบันทึก..." : "บันทึก"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {settingsModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="max-h-[92vh] w-full max-w-4xl overflow-auto rounded-lg bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-lg font-black text-slate-950">ตั้งค่า stock ร้านอาหาร</h2>
                <p className="text-sm text-slate-500">จัดการหมวดหมู่วัตถุดิบและหน่วยนับที่ใช้กับสูตร/คลัง</p>
              </div>
              <Button type="button" variant="outline" size="icon" className="h-9 w-9" onClick={() => setSettingsModalOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="grid gap-5 p-5 lg:grid-cols-2">
              <section className="rounded-lg border border-slate-200 p-4">
                <h3 className="font-black text-slate-950">หมวดหมู่วัตถุดิบ</h3>
                <div className="mt-3 grid gap-2">
                  <Input
                    value={categoryForm.name}
                    onChange={(event) => setCategoryForm((prev) => ({ ...prev, name: event.target.value }))}
                    placeholder="ชื่อหมวดหมู่"
                  />
                  <Input
                    value={categoryForm.code}
                    onChange={(event) => setCategoryForm((prev) => ({ ...prev, code: event.target.value }))}
                    placeholder="รหัสหมวดหมู่"
                  />
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      className="bg-blue-600 hover:bg-blue-700"
                      disabled={!categoryForm.name.trim() || categoryMutation.isPending}
                      onClick={() => categoryMutation.mutate()}
                    >
                      {categoryMutation.isPending ? "กำลังบันทึก..." : categoryForm.id ? "บันทึกหมวด" : "เพิ่มหมวด"}
                    </Button>
                    {categoryForm.id ? (
                      <Button type="button" variant="outline" onClick={() => setCategoryForm(EMPTY_CATEGORY_FORM)}>ล้าง</Button>
                    ) : null}
                  </div>
                </div>
                <div className="mt-4 max-h-72 divide-y divide-slate-100 overflow-auto rounded-md border border-slate-200">
                  {(categoriesQuery.data ?? []).map((category) => (
                    <div
                      key={category.id}
                      className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-slate-50"
                    >
                      <span>
                        <span className="block font-semibold text-slate-950">{category.name}</span>
                        <span className="text-xs text-slate-500">{category.code || "-"}</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          aria-label={`แก้ไขหมวดหมู่ ${category.name}`}
                          title="แก้ไข"
                          onClick={() => setCategoryForm({ id: category.id, name: category.name, code: category.code ?? "" })}
                        >
                          <Pencil className="h-4 w-4 text-blue-600" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                          aria-label={`ลบหมวดหมู่ ${category.name}`}
                          title="ลบ"
                          disabled={deleteCategoryMutation.isPending}
                          onClick={() => confirmDeleteCategory(category)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </span>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-lg border border-slate-200 p-4">
                <h3 className="font-black text-slate-950">หน่วยนับ</h3>
                <div className="mt-3 grid gap-2">
                  <Input
                    value={unitForm.code}
                    onChange={(event) => setUnitForm((prev) => ({ ...prev, code: event.target.value }))}
                    placeholder="รหัสหน่วย เช่น g, kg, bag"
                  />
                  <Input
                    value={unitForm.name}
                    onChange={(event) => setUnitForm((prev) => ({ ...prev, name: event.target.value }))}
                    placeholder="ชื่อหน่วย"
                  />
                  <Input
                    type="number"
                    min="0"
                    max="6"
                    value={unitForm.decimal_places}
                    onChange={(event) => setUnitForm((prev) => ({ ...prev, decimal_places: event.target.value }))}
                    placeholder="ทศนิยม"
                  />
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      className="bg-blue-600 hover:bg-blue-700"
                      disabled={!unitForm.code.trim() || !unitForm.name.trim() || unitMutation.isPending}
                      onClick={() => unitMutation.mutate()}
                    >
                      {unitMutation.isPending ? "กำลังบันทึก..." : unitForm.id ? "บันทึกหน่วย" : "เพิ่มหน่วย"}
                    </Button>
                    {unitForm.id ? (
                      <Button type="button" variant="outline" onClick={() => setUnitForm(EMPTY_UNIT_FORM)}>ล้าง</Button>
                    ) : null}
                  </div>
                </div>
                <div className="mt-4 max-h-72 divide-y divide-slate-100 overflow-auto rounded-md border border-slate-200">
                  {(unitsQuery.data ?? []).map((unit) => (
                    <div
                      key={unit.id}
                      className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-slate-50"
                    >
                      <span>
                        <span className="block font-semibold text-slate-950">{unit.name}</span>
                        <span className="text-xs text-slate-500">{unit.code} · ทศนิยม {unit.decimal_places}</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          aria-label={`แก้ไขหน่วยนับ ${unit.name}`}
                          title="แก้ไข"
                          onClick={() => setUnitForm({
                            id: unit.id,
                            code: unit.code,
                            name: unit.name,
                            decimal_places: String(unit.decimal_places ?? 0),
                          })}
                        >
                          <Pencil className="h-4 w-4 text-blue-600" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                          aria-label={`ลบหน่วยนับ ${unit.name}`}
                          title="ลบ"
                          disabled={deleteUnitMutation.isPending}
                          onClick={() => confirmDeleteUnit(unit)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </div>
      ) : null}

      {historyProduct ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="max-h-[92vh] w-full max-w-3xl overflow-auto rounded-lg bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-lg font-black text-slate-950">ประวัติ stock</h2>
                <p className="text-sm text-slate-500">{historyProduct.product.name} · {historyProduct.product.sku}</p>
              </div>
              <Button type="button" variant="outline" size="icon" className="h-9 w-9" onClick={() => setHistoryProduct(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="p-5">
              {movementsQuery.isLoading ? (
                <div className="flex h-32 items-center justify-center text-slate-500">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  โหลดประวัติ
                </div>
              ) : (movementsQuery.data ?? []).length > 0 ? (
                <div className="overflow-x-auto rounded-md border border-slate-200">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 text-left text-xs font-bold uppercase text-slate-500">
                      <tr>
                        <th className="px-3 py-2">เวลา</th>
                        <th className="px-3 py-2">ประเภท</th>
                        <th className="px-3 py-2 text-right">ก่อน</th>
                        <th className="px-3 py-2 text-right">เปลี่ยน</th>
                        <th className="px-3 py-2 text-right">หลัง</th>
                        <th className="px-3 py-2">หมายเหตุ</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(movementsQuery.data ?? []).map((movement) => (
                        <tr key={movement.id}>
                          <td className="px-3 py-2 text-slate-600">{new Date(movement.created_at).toLocaleString("th-TH")}</td>
                          <td className="px-3 py-2 font-semibold text-slate-950">{movement.movement_type}</td>
                          <td className="px-3 py-2 text-right">{formatQty(Number(movement.qty_before || 0))}</td>
                          <td className={`px-3 py-2 text-right font-bold ${Number(movement.qty || 0) < 0 ? "text-rose-700" : "text-emerald-700"}`}>
                            {formatQty(Number(movement.qty || 0))}
                          </td>
                          <td className="px-3 py-2 text-right">{formatQty(Number(movement.qty_after || 0))}</td>
                          <td className="px-3 py-2 text-slate-600">{movement.note || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="rounded-lg border border-slate-200 p-8 text-center text-slate-500">ยังไม่มีประวัติ stock</div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
