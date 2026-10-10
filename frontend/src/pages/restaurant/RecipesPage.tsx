import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChefHat, Pencil, Plus, Trash2, TrendingUp, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { useAuthStore } from "@/stores/auth.store";
import { authApi } from "@/lib/api";
import RecipeMaterialPicker, { type QuickMaterial } from "@/components/restaurant/RecipeMaterialPicker";
import { recipeQuantity, recipeError } from "@/lib/recipeUnits";
import type { ProductListItem } from "@/types/product";

type RecipeIngredientDraft = {
  row_id: string;
  cost_unit: string;
  ingredient_id: string;
  ingredient_name: string;
  quantity: string;
  unit: string;
  cost_price: string;
  image_url: string | null;
  image_file: File | null;
};

type RecipeListItem = {
  id: string;
  product_id: string;
  product_name: string;
  name: string;
  recipe_type: "menu_recipe" | "production_recipe" | string;
  version_no: number;
  yield_unit: string;
  is_active: boolean;
  total_cost: number;
  selling_price: number;
  gross_margin_pct: number;
};

type RecipeRead = RecipeListItem & {
  yield_qty: number;
  loss_percent: number;
  effective_yield_qty: number;
  effective_from: string | null;
  effective_to: string | null;
  notes: string | null;
  ingredients: {
    id: string;
    ingredient_id: string;
    ingredient_name: string;
    ingredient_sku: string;
    image_url: string | null;
    quantity: number;
    unit: string;
    latest_unit_cost: number;
    cost_per_recipe: number;
    cost_source: "received_purchase_order" | "product_cost_fallback";
    cost_source_reference: string;
    cost_unit: string;
    cost_source_unit: string;
    normalized_quantity: number;
    conversion_factor: number;
  }[];
  cost_per_yield: number;
  inventory_updates?: {
    product_id: string;
    product_name: string;
    inventory_role: "central_raw" | "central_ready" | "store_local";
    location_id: string;
    location_name: string;
    role_assigned: boolean;
    balance_created: boolean;
  }[];
};

const api = authApi;

function recipeBasePath(brandSlug?: string): string {
  return brandSlug ? `/restaurant/central/${brandSlug}` : "/restaurant";
}

async function fetchRecipes(branchId?: string, brandSlug?: string): Promise<RecipeListItem[]> {
  if (brandSlug) {
    const res = await api.get(`${recipeBasePath(brandSlug)}/recipes`);
    return res.data.data as RecipeListItem[];
  }
  const params = branchId ? `?branch_id=${branchId}` : "";
  const res = await api.get(`/restaurant/recipes${params}`);
  return res.data.data as RecipeListItem[];
}

async function fetchRecipe(id: string, brandSlug?: string): Promise<RecipeRead> {
  const res = await api.get(`${recipeBasePath(brandSlug)}/recipes/${id}`);
  return res.data.data as RecipeRead;
}

async function fetchRecipeProducts(brandSlug?: string, productType?: string): Promise<ProductListItem[]> {
  const products: ProductListItem[] = [];
  for (let page = 1; ; page++) {
    const response = await api.get(`${recipeBasePath(brandSlug)}/recipe-products`, {
      params: { page, limit: 200, ...(productType ? { product_type: productType } : {}) },
    });
    const rows = response.data.data as ProductListItem[];
    products.push(...rows);
    if (rows.length < 200) return products;
  }
}

const getApiErrorMessage = recipeError;

function MarginBadge({ pct }: { pct: number }): JSX.Element {
  const color = pct >= 60 ? "bg-emerald-100 text-emerald-700" : pct >= 40 ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${color}`}>{Number(pct).toFixed(1)}%</span>;
}

function recipeTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    menu_recipe: "สูตรเมนูหน้าร้าน",
    production_recipe: "สูตรผลิตครัวกลาง",
  };
  return labels[type] ?? type;
}

export default function RecipesPage({ brandSlug: brandOverride, companyKitchen = false, writesAllowed = true, onDraftChange }: {
  brandSlug?: string; companyKitchen?: boolean; writesAllowed?: boolean; onDraftChange?: (dirty: boolean) => void;
} = {}): JSX.Element {
  const { brandSlug: routeBrandSlug } = useParams<{ brandSlug?: string }>();
  const brandSlug = brandOverride ?? routeBrandSlug;
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const branchId = useAuthStore((s) => s.branchId);
  const companyId = useAuthStore(s => s.companyId);
  const signedBrandId = useAuthStore(s => s.brandId);
  const hasPermission = useAuthStore(s => s.hasPermission);
  const canManage = hasPermission("fb.recipe.manage") && writesAllowed;
  const scopeKey = `${companyId}:${signedBrandId}:${brandSlug ?? branchId ?? "global"}`;
  const isBrandCentral = Boolean(brandSlug);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [activeRecipeType, setActiveRecipeType] = useState<"production_recipe" | "menu_recipe">(
    brandSlug ? "production_recipe" : "menu_recipe"
  );

  // Form state
  const [formProductId, setFormProductId] = useState("");
  const [formRecipeType, setFormRecipeType] = useState<"menu_recipe" | "production_recipe">("menu_recipe");
  const [formVersionNo, setFormVersionNo] = useState("1");
  const [formEffectiveFrom, setFormEffectiveFrom] = useState("");
  const [formEffectiveTo, setFormEffectiveTo] = useState("");
  const [formName, setFormName] = useState("");
  const [formSellingPrice, setFormSellingPrice] = useState("0");
  const [formYieldQty, setFormYieldQty] = useState("1");
  const [formYieldUnit, setFormYieldUnit] = useState(brandSlug ? "kg" : "จาน");
  const [formLossPercent, setFormLossPercent] = useState("0");
  const [formNotes, setFormNotes] = useState("");
  const [formIngredients, setFormIngredients] = useState<RecipeIngredientDraft[]>([]);
  const [createdCount, setCreatedCount] = useState(0);
  useEffect(() => { onDraftChange?.(showForm); }, [showForm, onDraftChange]);

  const listQuery = useQuery({
    queryKey: ["recipes", scopeKey],
    queryFn: () => fetchRecipes(isBrandCentral ? undefined : branchId ?? undefined, brandSlug),
  });

  const detailQuery = useQuery({
    queryKey: ["recipe", scopeKey, selectedId],
    queryFn: () => fetchRecipe(selectedId!, brandSlug),
    enabled: Boolean(selectedId),
  });

  const menuQuery = useQuery({
    queryKey: ["products", "recipe_targets", scopeKey],
    queryFn: () => fetchRecipeProducts(brandSlug),
    enabled: showForm,
  });

  const rawQuery = useQuery({
    queryKey: ["products", "raw_material", scopeKey],
    queryFn: () => fetchRecipeProducts(brandSlug, "raw_material"),
    enabled: showForm,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      validateDraft();
      const response = await api.post(`${recipeBasePath(brandSlug)}/recipes`, {
        product_id: formProductId,
        branch_id: isBrandCentral ? null : branchId ?? null,
        selling_price: Number(formSellingPrice || 0),
        recipe_type: formRecipeType,
        version_no: Number(formVersionNo || 1),
        effective_from: formEffectiveFrom || null,
        effective_to: formEffectiveTo || null,
        name: formName,
        yield_qty: Number(formYieldQty),
        yield_unit: formYieldUnit,
        loss_percent: Number(formLossPercent || 0),
        notes: formNotes || null,
        ingredients: formIngredients
          .filter((i) => i.ingredient_id && Number(i.quantity) > 0)
          .map((i, idx) => ({
            ingredient_id: i.ingredient_id,
            quantity: Number(i.quantity),
            unit: i.unit,
            sort_order: idx,
          })),
      });
      return response.data.data as RecipeRead;
    },
    onSuccess: async (savedRecipe) => {
      await queryClient.invalidateQueries({ queryKey: ["recipes"] });
      await queryClient.invalidateQueries({ queryKey: ["products", "raw_material"] });
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
      await queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock"] });
      const createdBalances = savedRecipe.inventory_updates?.filter((item) => item.balance_created) ?? [];
      toast({
        title: "บันทึกสูตรแล้ว",
        description: `ผูกสูตร ${formName} แล้ว · เพิ่มวัตถุดิบ ${createdCount} รายการ · สร้างยอดสต็อกเริ่ม 0 เพิ่ม ${createdBalances.length} รายการ`,
      });
      resetForm();
    },
    onError: (error) => toast({ title: "บันทึกไม่สำเร็จ", description: getApiErrorMessage(error) || "กรุณาลองใหม่", variant: "destructive" }),
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editingId) return;
      validateDraft();
      const response = await api.patch(`${recipeBasePath(brandSlug)}/recipes/${editingId}`, {
        name: formName,
        selling_price: Number(formSellingPrice || 0),
        recipe_type: formRecipeType,
        version_no: Number(formVersionNo || 1),
        effective_from: formEffectiveFrom || null,
        effective_to: formEffectiveTo || null,
        yield_qty: Number(formYieldQty),
        yield_unit: formYieldUnit,
        loss_percent: Number(formLossPercent || 0),
        notes: formNotes || null,
        ingredients: formIngredients
          .filter((i) => i.ingredient_id && Number(i.quantity) > 0)
          .map((i, idx) => ({
            ingredient_id: i.ingredient_id,
            quantity: Number(i.quantity),
            unit: i.unit,
            sort_order: idx,
          })),
      });
      return response.data.data as RecipeRead;
    },
    onSuccess: async (savedRecipe) => {
      await queryClient.invalidateQueries({ queryKey: ["recipes"] });
      await queryClient.invalidateQueries({ queryKey: ["products", "raw_material"] });
      await queryClient.invalidateQueries({ queryKey: ["recipe", scopeKey, editingId] });
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
      await queryClient.invalidateQueries({ queryKey: ["restaurant-central-stock"] });
      const createdBalances = savedRecipe?.inventory_updates?.filter((item) => item.balance_created) ?? [];
      toast({
        title: "อัปเดตสูตรแล้ว",
        description: `ผูกสูตร ${formName} แล้ว · เพิ่มวัตถุดิบ ${createdCount} รายการ · สร้างยอดสต็อกเริ่ม 0 เพิ่ม ${createdBalances.length} รายการ`,
      });
      resetForm();
    },
    onError: (error) => toast({ title: "อัปเดตไม่สำเร็จ", description: getApiErrorMessage(error) || "กรุณาลองใหม่", variant: "destructive" }),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => api.delete(`${recipeBasePath(brandSlug)}/recipes/${id}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["recipes"] });
      setSelectedId(null);
      toast({ title: "ลบสูตรแล้ว" });
    },
  });

  function resetForm(): void {
    setShowForm(false);
    setEditingId(null);
    setFormProductId("");
    setFormRecipeType(activeRecipeType);
    setFormVersionNo("1");
    setFormEffectiveFrom("");
    setFormEffectiveTo("");
    setFormName("");
    setFormSellingPrice("0");
    setFormYieldQty("1");
    setFormYieldUnit(activeRecipeType === "production_recipe" ? "kg" : "จาน");
    setFormLossPercent("0");
    setFormNotes("");
    setFormIngredients([]);
    setCreatedCount(0);
  }

  function startCreate(recipeType = activeRecipeType): void {
    setEditingId(null);
    setShowForm(true);
    setFormProductId("");
    setFormRecipeType(recipeType);
    setFormVersionNo("1");
    setFormEffectiveFrom("");
    setFormEffectiveTo("");
    setFormName("");
    setFormSellingPrice("0");
    setFormYieldQty("1");
    setFormYieldUnit(recipeType === "production_recipe" ? "kg" : "จาน");
    setFormLossPercent("0");
    setFormNotes("");
    setFormIngredients([]);
    setCreatedCount(0);
  }

  function startEdit(recipe: RecipeRead): void {
    setEditingId(recipe.id);
    setShowForm(true);
    setFormProductId(recipe.product_id);
    setFormRecipeType(recipe.recipe_type === "production_recipe" ? "production_recipe" : "menu_recipe");
    setFormVersionNo(String(recipe.version_no));
    setFormEffectiveFrom(recipe.effective_from ?? "");
    setFormEffectiveTo(recipe.effective_to ?? "");
    setFormName(recipe.name);
    setFormSellingPrice(String(recipe.selling_price ?? 0));
    setFormYieldQty(String(recipe.yield_qty));
    setFormYieldUnit(recipe.yield_unit);
    setFormLossPercent(String(recipe.loss_percent ?? 0));
    setFormNotes(recipe.notes ?? "");
    setFormIngredients(
      recipe.ingredients.map((ing) => ({
        row_id: crypto.randomUUID(),
        cost_unit: ing.cost_unit || ing.unit,
        ingredient_id: ing.ingredient_id,
        ingredient_name: ing.ingredient_name,
        quantity: String(ing.quantity),
        unit: ing.unit,
        cost_price: String(ing.latest_unit_cost ?? 0),
        image_url: ing.image_url,
        image_file: null,
      }))
    );
  }

  function addIngredient(): void {
    setFormIngredients((prev) => [...prev, { row_id: crypto.randomUUID(), cost_unit: "", ingredient_id: "", ingredient_name: "", quantity: "1", unit: "g", cost_price: "0", image_url: null, image_file: null }]);
  }

  function updateIngredient(index: number, key: keyof RecipeIngredientDraft, value: string | File | null): void {
    setFormIngredients((prev) =>
      prev.map((item, i) => (i === index ? { ...item, [key]: value } : item))
    );
  }

  function removeIngredient(index: number): void {
    setFormIngredients((prev) => prev.filter((_, i) => i !== index));
  }

  function chooseIngredient(index: number, product: ProductListItem): void {
    setFormIngredients(previous => previous.map((row, i) => i === index ? {
      ...row, ingredient_id: product.id, ingredient_name: product.name,
      unit: product.unit?.code ?? "", cost_unit: product.unit?.code ?? "",
      cost_price: String(product.cost_price ?? 0), image_url: product.image_url, image_file: null,
    } : row));
    const rowId = formIngredients[index]?.row_id;
    window.requestAnimationFrame(() => document.getElementById(`recipe-quantity-${rowId}`)?.focus());
  }

  function materialCreated(index: number, product: QuickMaterial): void {
    queryClient.setQueryData<ProductListItem[]>(["products", "raw_material", scopeKey], previous =>
      [...(previous ?? []).filter(row => row.id !== product.id), product]);
    chooseIngredient(index, product);
    setCreatedCount(count => count + 1);
    const setup = product.inventory_setup;
    toast({ title: `เพิ่ม ${product.name} เข้าแถวสูตรแล้ว`, description:
      `สร้างยอดสต็อกเริ่ม 0 จำนวน ${setup?.zero_balances_created ?? 0} รายการ${setup?.mapping_created ? " · ผูกครัวกลางกับแบรนด์แล้ว" : ""}${setup?.stock_deferred ? " · ยังไม่ระบุคลัง จึงยังไม่สร้างยอดสต็อก" : ""}` });
  }

  function validateDraft(): void {
    if (!canManage) throw new Error("ไม่มีสิทธิ์จัดการสูตร");
    if (!formProductId || !formName.trim()) throw new Error("กรุณาเลือกเมนูและระบุชื่อสูตร");
    if (!Number.isFinite(Number(formYieldQty)) || Number(formYieldQty) <= 0 || !formYieldUnit.trim()) throw new Error("กรุณาระบุจำนวนที่ผลิตได้และหน่วยให้ครบ");
    if (!Number.isFinite(Number(formLossPercent)) || Number(formLossPercent) < 0 || Number(formLossPercent) >= 100) throw new Error("การสูญเสียต้องอยู่ระหว่าง 0 ถึงน้อยกว่า 100%");
    if (!Number.isFinite(Number(formSellingPrice)) || Number(formSellingPrice) < 0) throw new Error("ราคาขายต้องไม่ติดลบ");
    if (!formIngredients.length) throw new Error("กรุณาเพิ่มวัตถุดิบอย่างน้อย 1 รายการ");
    const seen = new Set<string>();
    for (const row of formIngredients) {
      if (!row.ingredient_id || !Number.isFinite(Number(row.quantity)) || Number(row.quantity) <= 0) throw new Error("กรุณาเลือกวัตถุดิบและใส่ปริมาณมากกว่า 0 ทุกแถว");
      if (seen.has(row.ingredient_id)) throw new Error(`มี ${row.ingredient_name} ซ้ำ กรุณารวมปริมาณในแถวเดียว`);
      seen.add(row.ingredient_id);
      recipeQuantity(Number(row.quantity), row.unit, row.cost_unit);
    }
  }

  const recipes = listQuery.data ?? [];
  const productionCount = recipes.filter((recipe) => recipe.recipe_type === "production_recipe").length;
  const menuCount = recipes.filter((recipe) => recipe.recipe_type !== "production_recipe").length;
  const visibleRecipes = recipes.filter((recipe) =>
    activeRecipeType === "production_recipe"
      ? recipe.recipe_type === "production_recipe"
      : recipe.recipe_type !== "production_recipe"
  );
  const selected = detailQuery.data ?? null;
  const rawMaterials = rawQuery.data ?? [];
  const recipeProducts = menuQuery.data ?? [];
  const preview = useMemo(() => {
    const totalCost = formIngredients.reduce((sum, ing) => {
      if (!ing.ingredient_id) return sum;
      try { return sum + recipeQuantity(Number(ing.quantity || 0), ing.unit, ing.cost_unit) * Number(ing.cost_price || 0); }
      catch { return sum; }
    }, 0);
    const yieldQty = Math.max(Number(formYieldQty || 1), 0.0001);
    const lossRate = Math.min(Math.max(Number(formLossPercent || 0), 0), 100);
    const effectiveYield = Math.max(yieldQty * (1 - lossRate / 100), 0.0001);
    return {
      totalCost,
      effectiveYield,
      costPerYield: totalCost / effectiveYield,
      grossMarginPct: Number(formSellingPrice || 0) > 0
        ? ((Number(formSellingPrice || 0) - (totalCost / effectiveYield)) / Number(formSellingPrice || 0)) * 100
        : 0,
    };
  }, [formIngredients, formLossPercent, formSellingPrice, formYieldQty, rawMaterials]);

  useEffect(() => {
    if (!selectedId) return;
    if (!visibleRecipes.some((recipe) => recipe.id === selectedId)) {
      setSelectedId(visibleRecipes[0]?.id ?? null);
    }
  }, [selectedId, visibleRecipes]);

  return (
    <div>
      <PageHeader
        title={isBrandCentral ? `สูตรแบรนด์ ${brandSlug}` : "สูตรอาหาร / เครื่องดื่ม"}
        subtitle={isBrandCentral ? "แยกสูตรผลิตครัวกลางออกจากสูตรเมนูหน้าร้าน เพื่อควบคุมต้นทุนและสูตรลับให้ชัดเจน" : "จัดการสูตร ต้นทุนวัตถุดิบ และ Gross Margin"}
        actions={
          <Button disabled={!canManage || showForm} className="bg-orange-500 hover:bg-orange-600" onClick={() => startCreate()}>
            <Plus className="mr-2 h-4 w-4" />
            สร้างสูตรใหม่
          </Button>
        }
      />

      <div className="flex min-w-0 flex-col gap-4 p-3 md:p-6 xl:flex-row">
        {/* Recipe List */}
        <div className={`flex shrink-0 flex-col gap-2 ${showForm ? "hidden" : "w-full xl:w-72"}`}>
          {!companyKitchen ? (
            <div className="mb-2 grid grid-cols-2 gap-2 rounded-lg border border-slate-200 bg-white p-1">
              <button
                type="button"
                className={`rounded-md px-3 py-2 text-sm font-bold ${activeRecipeType === "production_recipe" ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-slate-50"}`}
                onClick={() => {
                  setActiveRecipeType("production_recipe");
                  setShowForm(false);
                }}
              >
                ผลิต {productionCount}
              </button>
              <button
                type="button"
                className={`rounded-md px-3 py-2 text-sm font-bold ${activeRecipeType === "menu_recipe" ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-slate-50"}`}
                onClick={() => {
                  setActiveRecipeType("menu_recipe");
                  setShowForm(false);
                }}
              >
                เมนู {menuCount}
              </button>
            </div>
          ) : null}
          {isBrandCentral ? (
            <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
              {activeRecipeType === "production_recipe"
                ? "ส่วนกลางเห็นสูตรลึก เช่น ซอสพื้นฐานและวัตถุดิบเตรียม"
                : "หน้าร้านเห็น BOM ของแต่ละเมนูและปริมาณวัตถุดิบที่ใช้"}
            </div>
          ) : null}
          {listQuery.isLoading && <p className="text-sm text-slate-500">กำลังโหลด...</p>}
          {visibleRecipes.length === 0 && !listQuery.isLoading && (
            <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-slate-400">
              <ChefHat className="mx-auto mb-2 h-8 w-8" />
              <p className="text-sm">ยังไม่มีสูตร</p>
              <p className="mt-1 text-xs">กดปุ่ม "สร้างสูตรใหม่" ด้านบน</p>
            </div>
          )}
          {visibleRecipes.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setSelectedId(r.id)}
              className={`rounded-2xl border p-4 text-left transition-all hover:-translate-y-0.5 ${selectedId === r.id ? "border-orange-400 bg-orange-50 shadow-md" : "border-slate-200 bg-white hover:border-slate-300"}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-900">{r.product_name}</p>
                  <p className="text-xs text-slate-500">{r.name}</p>
                </div>
                <MarginBadge pct={r.gross_margin_pct} />
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">{recipeTypeLabel(r.recipe_type)}</span>
                <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700">v{r.version_no}</span>
              </div>
              <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
                <span>ต้นทุน ฿{Number(r.total_cost).toFixed(2)}</span>
                <span>ขาย ฿{Number(r.selling_price).toFixed(2)}</span>
              </div>
            </button>
          ))}
        </div>

        {/* Recipe Detail */}
        {selected && !showForm && (
          <div className="flex-1 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-slate-900">{selected.product_name}</h2>
                <p className="mt-0.5 text-sm text-slate-500">
                  {selected.name} • {recipeTypeLabel(selected.recipe_type)} • v{selected.version_no}
                </p>
                <p className="mt-0.5 text-xs text-slate-400">
                  Yield {selected.yield_qty} {selected.yield_unit} · หลัง loss {Number(selected.effective_yield_qty).toFixed(4)} {selected.yield_unit}
                  {selected.effective_from ? ` · เริ่ม ${selected.effective_from}` : ""}
                  {selected.effective_to ? ` · ถึง ${selected.effective_to}` : ""}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  aria-label="แก้ไขสูตร"
                  disabled={!canManage}
                  onClick={() => startEdit(selected)}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600 hover:bg-red-50"
                  disabled={!canManage}
                  onClick={() => window.confirm("ลบสูตรนี้หรือไม่?") && deleteMutation.mutate(selected.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Cost Summary */}
            <div className="mt-6 grid gap-3 md:grid-cols-3 md:gap-4">
              <div className="rounded-2xl bg-slate-50 p-4 text-center">
                <p className="text-xs uppercase tracking-wider text-slate-500">ต้นทุนรวม</p>
                <p className="mt-1 text-2xl font-bold text-slate-900">฿{Number(selected.cost_per_yield).toFixed(2)}</p>
                <p className="text-xs text-slate-400">ต่อ {selected.yield_unit} · loss {Number(selected.loss_percent).toFixed(2)}%</p>
              </div>
              <div className="rounded-2xl bg-blue-50 p-4 text-center">
                <p className="text-xs uppercase tracking-wider text-blue-600">ราคาขาย</p>
                <p className="mt-1 text-2xl font-bold text-blue-700">฿{Number(selected.selling_price).toFixed(2)}</p>
              </div>
              <div className={`rounded-2xl p-4 text-center ${selected.gross_margin_pct >= 60 ? "bg-emerald-50" : selected.gross_margin_pct >= 40 ? "bg-amber-50" : "bg-red-50"}`}>
                <p className={`text-xs uppercase tracking-wider ${selected.gross_margin_pct >= 60 ? "text-emerald-600" : selected.gross_margin_pct >= 40 ? "text-amber-600" : "text-red-600"}`}>
                  <TrendingUp className="mr-1 inline h-3 w-3" />
                  Gross Margin
                </p>
                <p className={`mt-1 text-2xl font-bold ${selected.gross_margin_pct >= 60 ? "text-emerald-700" : selected.gross_margin_pct >= 40 ? "text-amber-700" : "text-red-700"}`}>
                  {Number(selected.gross_margin_pct).toFixed(1)}%
                </p>
              </div>
            </div>

            {/* Ingredients Table */}
            <div className="mt-6">
              <h3 className="mb-3 font-semibold text-slate-800">วัตถุดิบ</h3>
              <div className="app-horizontal-scroll overflow-x-auto rounded-2xl border border-slate-200">
                <table className="w-full min-w-[680px] text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="px-4 py-3 text-left">วัตถุดิบ</th>
                      <th className="px-4 py-3 text-right">ปริมาณ</th>
                      <th className="px-4 py-3 text-right">ราคา/หน่วย</th>
                      <th className="px-4 py-3 text-right">ต้นทุน</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {selected.ingredients.map((ing) => (
                      <tr key={ing.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-medium text-slate-800">
                          {ing.ingredient_name}
                          <span className="ml-2 text-xs text-slate-400">{ing.ingredient_sku}</span>
                          <p className="mt-1 text-xs font-normal text-slate-400">
                            {ing.cost_source === "received_purchase_order" ? `รับซื้อ ${ing.cost_source_reference}` : `ต้นทุนสินค้า ${ing.cost_source_reference}`}
                          </p>
                        </td>
                        <td className="px-4 py-3 text-right text-slate-600">
                          {ing.quantity} {ing.unit}
                          {ing.conversion_factor !== 1 ? (
                            <p className="text-xs text-slate-400">= {ing.normalized_quantity} {ing.cost_unit}</p>
                          ) : null}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-600">
                          ฿{Number(ing.latest_unit_cost).toFixed(4)}/{ing.cost_unit}
                        </td>
                        <td className="px-4 py-3 text-right font-medium text-slate-800">
                          ฿{Number(ing.cost_per_recipe).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                    <tr className="bg-slate-50 font-semibold">
                      <td colSpan={3} className="px-4 py-3 text-right text-slate-700">รวมต้นทุน</td>
                      <td className="px-4 py-3 text-right text-orange-700">฿{Number(selected.total_cost).toFixed(2)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {selected.notes && (
              <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">{selected.notes}</p>
            )}
          </div>
        )}

        {/* Single-page recipe editor: technical settings stay collapsed. */}
        {showForm && (
          <div className="min-w-0 flex-1 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm md:p-6">
            <div className="flex items-center justify-between gap-2"><h2 className="text-xl font-semibold">{editingId ? "แก้ไขสูตร" : "สร้างสูตรใหม่"}</h2>
              <Button aria-label="ปิดแบบฟอร์มสูตร" variant="ghost" onClick={resetForm}><X className="h-5 w-5" /></Button></div>
            <p className="mt-2 text-sm text-slate-500">เลือกเมนู → เพิ่มวัตถุดิบ → ใส่ปริมาณ → ดูต้นทุน → บันทึกสูตร</p>
            <div className="mt-5 space-y-5">
              <div className="grid gap-3 sm:grid-cols-2">
                <Label htmlFor="recipe-type">ประเภทสูตร<select id="recipe-type" className="mt-1 h-11 w-full rounded-xl border px-3" disabled={companyKitchen || Boolean(editingId)}
                  value={formRecipeType} onChange={e => setFormRecipeType(e.target.value as "menu_recipe" | "production_recipe")}>
                  <option value="menu_recipe">สูตรเมนูหน้าร้าน</option><option value="production_recipe">สูตรผลิตครัวกลาง</option></select></Label>
                <Label htmlFor="recipe-product">{formRecipeType === "production_recipe" ? "สินค้าที่ผลิต" : "เมนูหน้าร้าน"}
                  <select id="recipe-product" className="mt-1 h-11 w-full rounded-xl border px-3" value={formProductId} disabled={Boolean(editingId)} onChange={e => {
                    const product = recipeProducts.find(p => p.id === e.target.value); setFormProductId(e.target.value);
                    if (product) { if (!formName) setFormName(`สูตร${product.name}`); setFormSellingPrice(String(product.selling_price ?? 0)); }
                  }}><option value="">เลือกเมนู / สินค้าที่ผลิต</option>{recipeProducts.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Label>
              </div>
              {menuQuery.isError || rawQuery.isError ? <p role="alert" className="text-red-700">โหลดรายการไม่สำเร็จ ข้อมูลสูตรยังอยู่ <button type="button" className="underline" onClick={() => { void menuQuery.refetch(); void rawQuery.refetch(); }}>ลองใหม่</button></p> : null}
              <div className="flex items-center justify-between gap-2"><h3 className="font-bold">วัตถุดิบในสูตร</h3><Button type="button" variant="outline" disabled={!canManage} onClick={addIngredient}><Plus className="mr-1 h-4 w-4" />เพิ่มวัตถุดิบ</Button></div>
              {formIngredients.length === 0 && <p className="text-sm text-slate-500">กดเพิ่มวัตถุดิบ แล้วพิมพ์ค้นหาได้เลย</p>}
              <div className="space-y-3">
                {formIngredients.map((row, index) => {
                  let unitError = "";
                  if (row.ingredient_id) { try { recipeQuantity(1, row.unit, row.cost_unit); } catch (error) { unitError = recipeError(error); } }
                  return <div key={row.row_id} data-testid="recipe-ingredient-row" className="rounded-2xl border bg-slate-50 p-3">
                    <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_110px_110px_auto]">
                      <RecipeMaterialPicker materials={rawMaterials} selectedId={row.ingredient_id} selectedName={row.ingredient_name}
                        endpoint={`${recipeBasePath(brandSlug)}/raw-materials/quick-create`}
                        role={formRecipeType === "production_recipe" ? "central_raw" : isBrandCentral ? "central_ready" : "store_local"}
                        companyKitchen={companyKitchen} disabled={!canManage}
                        onSelect={p => chooseIngredient(index, p)} onCreated={p => materialCreated(index, p)} />
                      <Label htmlFor={`recipe-quantity-${row.row_id}`}>ปริมาณ<Input id={`recipe-quantity-${row.row_id}`} type="number" min="0.0001" step="0.0001" value={row.quantity} onChange={e => updateIngredient(index, "quantity", e.target.value)} /></Label>
                      <Label htmlFor={`recipe-unit-${row.row_id}`}>หน่วย<Input id={`recipe-unit-${row.row_id}`} list="recipe-units" value={row.unit} onChange={e => updateIngredient(index, "unit", e.target.value)} /></Label>
                      <Button type="button" aria-label={`ลบวัตถุดิบแถว ${index + 1}`} variant="ghost" onClick={() => removeIngredient(index)}><X className="h-4 w-4" /></Button>
                    </div>
                    {unitError ? <p role="alert" className="mt-2 text-sm text-red-700">{unitError}</p> : row.ingredient_id ? <p className="mt-2 text-sm text-slate-500">ต้นทุนอ้างอิง ฿{Number(row.cost_price).toFixed(4)} / {row.cost_unit} · ในสูตร ฿{(recipeQuantity(Number(row.quantity || 0), row.unit, row.cost_unit) * Number(row.cost_price)).toFixed(2)}</p> : null}
                  </div>;
                })}
                <datalist id="recipe-units">{["kg", "g", "l", "ml", "ชิ้น"].map(u => <option key={u} value={u} />)}</datalist>
              </div>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Label htmlFor="recipe-yield">จำนวนที่ผลิตได้<Input id="recipe-yield" type="number" min="0.0001" step="0.0001" value={formYieldQty} onChange={e => setFormYieldQty(e.target.value)} /></Label>
                <Label htmlFor="recipe-yield-unit">หน่วยผลผลิต<Input id="recipe-yield-unit" value={formYieldUnit} onChange={e => setFormYieldUnit(e.target.value)} placeholder="จาน / ชิ้น / kg" /></Label>
                <Label htmlFor="recipe-loss">สูญเสีย (%)<Input id="recipe-loss" type="number" min="0" max="99.99" step="0.01" value={formLossPercent} onChange={e => setFormLossPercent(e.target.value)} /></Label>
                <Label htmlFor="recipe-selling">ราคาขายต่อหน่วย<Input id="recipe-selling" type="number" min="0" step="0.01" value={formSellingPrice} onChange={e => setFormSellingPrice(e.target.value)} /></Label>
              </div>
              <section aria-label="ต้นทุนสูตร" className="grid grid-cols-2 gap-3 rounded-2xl border border-orange-200 bg-orange-50 p-4 lg:grid-cols-4">
                <div><p className="text-sm">ต้นทุนรวม</p><p data-testid="recipe-total-cost" className="text-xl font-bold">฿{preview.totalCost.toFixed(2)}</p></div>
                <div><p className="text-sm">ผลผลิตหลังสูญเสีย</p><p className="text-xl font-bold">{preview.effectiveYield.toFixed(4)} {formYieldUnit}</p></div>
                <div><p className="text-sm">ต้นทุนต่อ {formYieldUnit || "หน่วย"}</p><p data-testid="recipe-unit-cost" className="text-xl font-bold">฿{preview.costPerYield.toFixed(2)}</p></div>
                <div><p className="text-sm">กำไรขั้นต้น (Gross margin)</p><p className="text-xl font-bold">{preview.grossMarginPct.toFixed(1)}%</p></div>
                <p className="col-span-2 text-xs text-slate-600 lg:col-span-4">ต้นทุนประมาณการจากข้อมูลที่แสดง ระบบคำนวณต้นทุนจากการรับซื้อล่าสุดอีกครั้งเมื่อบันทึก โดยไม่เปลี่ยนราคาวัตถุดิบเดิม</p>
              </section>
              <details className="rounded-xl border p-3"><summary className="cursor-pointer font-semibold">ตั้งค่าเพิ่มเติม</summary><div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Label htmlFor="recipe-name">ชื่อสูตร<Input id="recipe-name" value={formName} onChange={e => setFormName(e.target.value)} /></Label>
                <Label htmlFor="recipe-version">รุ่นสูตร<Input id="recipe-version" type="number" min="1" step="1" value={formVersionNo} onChange={e => setFormVersionNo(e.target.value)} /></Label>
                <Label htmlFor="recipe-from">วันที่เริ่มใช้<Input id="recipe-from" type="date" value={formEffectiveFrom} onChange={e => setFormEffectiveFrom(e.target.value)} /></Label>
                <Label htmlFor="recipe-to">วันที่เลิกใช้<Input id="recipe-to" type="date" value={formEffectiveTo} onChange={e => setFormEffectiveTo(e.target.value)} /></Label>
                <Label htmlFor="recipe-notes">หมายเหตุ<Input id="recipe-notes" value={formNotes} onChange={e => setFormNotes(e.target.value)} /></Label>
                <p className="text-xs text-slate-500">{isBrandCentral ? "สูตรนี้อยู่ในแบรนด์ที่เลือก" : branchId ? "สูตรนี้ใช้ในสาขาปัจจุบัน" : "สูตรนี้ใช้ร่วมกันในบริษัท"}</p>
              </div></details>
              <div className="sticky bottom-0 flex justify-end gap-3 bg-white py-3">
                <Button variant="outline" disabled={createMutation.isPending || updateMutation.isPending} onClick={resetForm}>ยกเลิก</Button>
                <Button disabled={!canManage || !formProductId || !formName || createMutation.isPending || updateMutation.isPending} onClick={() => editingId ? updateMutation.mutate() : createMutation.mutate()}>
                  {createMutation.isPending || updateMutation.isPending ? "กำลังบันทึก…" : editingId ? "อัปเดตสูตร" : "บันทึกสูตร"}</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
