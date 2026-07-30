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
import { productApi } from "@/lib/productApi";
import type { ProductListItem } from "@/types/product";

type RecipeIngredientDraft = {
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

type IngredientInventoryRole = "central_raw" | "central_ready" | "store_local";

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

async function fetchRecipeProducts(brandSlug?: string): Promise<ProductListItem[]> {
  if (brandSlug) {
    const res = await api.get(`${recipeBasePath(brandSlug)}/recipe-products`);
    return res.data.data as ProductListItem[];
  }
  const res = await api.get("/products?is_active=true&limit=300");
  return res.data.data as ProductListItem[];
}

async function fetchRawMaterials(brandSlug?: string): Promise<ProductListItem[]> {
  if (brandSlug) {
    const res = await api.get(`${recipeBasePath(brandSlug)}/recipe-products?product_type=raw_material`);
    return res.data.data as ProductListItem[];
  }
  const res = await api.get("/products?product_type=raw_material&is_active=true&limit=200");
  return res.data.data as ProductListItem[];
}

const UNIT_ALIASES: Record<string, string> = {
  "กรัม": "g",
  gram: "g",
  grams: "g",
  "ก": "g",
  "กก": "kg",
  "กิโล": "kg",
  "กิโลกรัม": "kg",
  kilogram: "kg",
  kilograms: "kg",
  "มล": "ml",
  "มิลลิลิตร": "ml",
  milliliter: "ml",
  milliliters: "ml",
  "ลิตร": "l",
  liter: "l",
  liters: "l",
  "ขีด": "heed",
};

const UNIT_TO_BASE: Record<string, [string, number]> = {
  g: ["weight", 1],
  kg: ["weight", 1000],
  heed: ["weight", 100],
  ml: ["volume", 1],
  l: ["volume", 1000],
};

function normalizeUnit(unit?: string | null): string {
  const raw = (unit ?? "").trim().toLowerCase();
  return UNIT_ALIASES[raw] ?? raw;
}

function convertQuantity(value: number, fromUnit?: string | null, toUnit?: string | null): number {
  const source = normalizeUnit(fromUnit);
  const target = normalizeUnit(toUnit);
  if (!source || !target || source === target) return value;
  const sourceBase = UNIT_TO_BASE[source];
  const targetBase = UNIT_TO_BASE[target];
  if (!sourceBase || !targetBase || sourceBase[0] !== targetBase[0]) return value;
  return (value * sourceBase[1]) / targetBase[1];
}

function getApiErrorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    return response?.data?.detail ?? "";
  }
  return error instanceof Error ? error.message : "";
}

function MarginBadge({ pct }: { pct: number }): JSX.Element {
  const color = pct >= 60 ? "bg-emerald-100 text-emerald-700" : pct >= 40 ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${color}`}>{pct.toFixed(1)}%</span>;
}

function recipeTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    menu_recipe: "สูตรเมนูหน้าร้าน",
    production_recipe: "สูตรผลิตส่วนกลาง",
  };
  return labels[type] ?? type;
}

export default function RecipesPage(): JSX.Element {
  const { brandSlug } = useParams<{ brandSlug?: string }>();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const branchId = useAuthStore((s) => s.branchId);
  const scopeKey = brandSlug ?? branchId ?? "global";
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
  const [formYieldUnit, setFormYieldUnit] = useState("แก้ว");
  const [formLossPercent, setFormLossPercent] = useState("0");
  const [formNotes, setFormNotes] = useState("");
  const [formIngredients, setFormIngredients] = useState<RecipeIngredientDraft[]>([]);
  const [rawName, setRawName] = useState("");
  const [rawSku, setRawSku] = useState("");
  const [rawCost, setRawCost] = useState("0");
  const [rawUnit, setRawUnit] = useState("g");
  const [rawInventoryRole, setRawInventoryRole] = useState<IngredientInventoryRole>("central_raw");
  const [rawImage, setRawImage] = useState<File | null>(null);

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
    queryFn: () => fetchRawMaterials(brandSlug),
    enabled: showForm,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      await syncRawMaterialDrafts();
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
        description: createdBalances.length > 0
          ? `เพิ่มรายการ stock เริ่มต้น 0 จำนวน ${createdBalances.length} รายการ`
          : undefined,
      });
      resetForm();
    },
    onError: (error) => toast({ title: "บันทึกไม่สำเร็จ", description: getApiErrorMessage(error) || "กรุณาลองใหม่", variant: "destructive" }),
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editingId) return;
      await syncRawMaterialDrafts();
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
        description: createdBalances.length > 0
          ? `เพิ่มรายการ stock เริ่มต้น 0 จำนวน ${createdBalances.length} รายการ`
          : undefined,
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

  const createRawMaterialMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post(`${recipeBasePath(brandSlug)}/raw-materials`, {
        sku: rawSku.trim(),
        name: rawName.trim(),
        cost_price: Number(rawCost || 0),
        unit: rawUnit.trim() || "unit",
        inventory_role: rawInventoryRole,
      });
      const product = res.data.data as ProductListItem;
      if (rawImage) {
        const upload = await productApi.uploadImage(product.id, rawImage, true);
        return upload.data.data as ProductListItem;
      }
      return product;
    },
    onSuccess: async (product) => {
      await queryClient.invalidateQueries({ queryKey: ["products", "raw_material", scopeKey] });
      setFormIngredients((prev) => [
        ...prev,
        {
          ingredient_id: product.id,
          ingredient_name: product.name,
          quantity: "1",
          unit: rawUnit,
          cost_price: String(product.cost_price ?? rawCost ?? 0),
          image_url: product.image_url ?? null,
          image_file: null,
        },
      ]);
      setRawName("");
      setRawSku("");
      setRawCost("0");
      setRawUnit("g");
      setRawInventoryRole(formRecipeType === "production_recipe" ? "central_raw" : "central_ready");
      setRawImage(null);
      toast({ title: "สร้างวัตถุดิบแล้ว" });
    },
    onError: () => toast({ title: "สร้างวัตถุดิบไม่สำเร็จ", description: "ตรวจ SKU ซ้ำหรือสิทธิ์จัดการสูตร" }),
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
    setFormYieldUnit("แก้ว");
    setFormLossPercent("0");
    setFormNotes("");
    setFormIngredients([]);
    setRawName("");
    setRawSku("");
    setRawCost("0");
    setRawUnit("g");
    setRawInventoryRole(activeRecipeType === "production_recipe" ? "central_raw" : "central_ready");
    setRawImage(null);
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
    setFormYieldUnit("แก้ว");
    setFormLossPercent("0");
    setFormNotes("");
    setFormIngredients([]);
    setRawName("");
    setRawSku("");
    setRawCost("0");
    setRawUnit("g");
    setRawInventoryRole(recipeType === "production_recipe" ? "central_raw" : "central_ready");
    setRawImage(null);
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
    setRawInventoryRole(recipe.recipe_type === "production_recipe" ? "central_raw" : "central_ready");
    setFormIngredients(
      recipe.ingredients.map((ing) => ({
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
    setFormIngredients((prev) => [...prev, { ingredient_id: "", ingredient_name: "", quantity: "1", unit: "g", cost_price: "0", image_url: null, image_file: null }]);
  }

  function updateIngredient(index: number, key: keyof RecipeIngredientDraft, value: string | File | null): void {
    setFormIngredients((prev) =>
      prev.map((item, i) => (i === index ? { ...item, [key]: value } : item))
    );
  }

  function removeIngredient(index: number): void {
    setFormIngredients((prev) => prev.filter((_, i) => i !== index));
  }

  async function syncRawMaterialDrafts(): Promise<void> {
    const seen = new Set<string>();
    for (const ingredient of formIngredients) {
      if (!ingredient.ingredient_id || seen.has(ingredient.ingredient_id)) continue;
      seen.add(ingredient.ingredient_id);

      const costPrice = Number(ingredient.cost_price || 0);
      await productApi.update(ingredient.ingredient_id, { cost_price: costPrice });
      if (ingredient.image_file) {
        await productApi.uploadImage(ingredient.ingredient_id, ingredient.image_file, true);
      }
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
      const product = rawMaterials.find((item) => item.id === ing.ingredient_id);
      if (!product) return sum;
      const qty = Number(ing.quantity || 0);
      const costQty = convertQuantity(qty, ing.unit, product.unit?.code ?? ing.unit);
      return sum + costQty * Number(ing.cost_price || product.cost_price || 0);
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
        subtitle={isBrandCentral ? "แยกสูตรผลิตส่วนกลางออกจากสูตรเมนูหน้าร้าน เพื่อควบคุมต้นทุนและสูตรลับให้ชัดเจน" : "จัดการสูตร ต้นทุนวัตถุดิบ และ Gross Margin"}
        actions={
          <Button className="bg-orange-500 hover:bg-orange-600" onClick={() => startCreate()}>
            <Plus className="mr-2 h-4 w-4" />
            สร้างสูตรใหม่
          </Button>
        }
      />

      <div className="flex gap-6 p-6">
        {/* Recipe List */}
        <div className="flex w-72 flex-shrink-0 flex-col gap-2">
          {isBrandCentral ? (
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
                  onClick={() => startEdit(selected)}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600 hover:bg-red-50"
                  onClick={() => window.confirm("ลบสูตรนี้หรือไม่?") && deleteMutation.mutate(selected.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Cost Summary */}
            <div className="mt-6 grid grid-cols-3 gap-4">
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
              <div className="overflow-hidden rounded-2xl border border-slate-200">
                <table className="w-full text-sm">
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
                        </td>
                        <td className="px-4 py-3 text-right text-slate-600">
                          {ing.quantity} {ing.unit}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-600">
                          ฿{Number(ing.latest_unit_cost).toFixed(4)}/{ing.unit}
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

        {/* Create/Edit Form */}
        {showForm && (
          <div className="flex-1 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-900">{editingId ? "แก้ไขสูตร" : "สร้างสูตรใหม่"}</h2>
              <Button variant="ghost" size="icon" onClick={resetForm}><X className="h-5 w-5" /></Button>
            </div>

            <div className="mt-6 space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>สินค้าที่ผูกสูตร</Label>
                  <select
                    className="mt-1 h-10 w-full rounded-xl border border-slate-300 px-3 text-sm"
                    value={formProductId}
                    disabled={Boolean(editingId)}
                    onChange={(e) => {
                      const p = recipeProducts.find((m) => m.id === e.target.value);
                      setFormProductId(e.target.value);
                      if (p && !formName) setFormName(`สูตร${p.name}`);
                      if (p) setFormSellingPrice(String(p.selling_price ?? 0));
                    }}
                  >
                    <option value="">-- เลือกสินค้า --</option>
                    {recipeProducts.map((m) => (
                      <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                  </select>
                  {recipeProducts.length === 0 && (
                    <p className="mt-1 text-xs text-amber-600">ยังไม่มีสินค้า active — เพิ่มสินค้าก่อน</p>
                  )}
                  {editingId && (
                    <p className="mt-1 text-xs text-slate-500">แก้ไขสูตรเดิมจะไม่เปลี่ยนเมนูที่ผูกไว้</p>
                  )}
                </div>
                <div>
                  <Label>ชื่อสูตร</Label>
                  <Input className="mt-1" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="เช่น Latte Standard" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>ประเภทสูตร</Label>
                  <select
                    className="mt-1 h-10 w-full rounded-xl border border-slate-300 px-3 text-sm"
                    value={formRecipeType}
                    onChange={(e) => {
                      const nextType = e.target.value === "production_recipe" ? "production_recipe" : "menu_recipe";
                      setFormRecipeType(nextType);
                      setRawInventoryRole(nextType === "production_recipe" ? "central_raw" : "central_ready");
                    }}
                  >
                    <option value="production_recipe">สูตรผลิตส่วนกลาง</option>
                    <option value="menu_recipe">สูตรเมนูหน้าร้าน</option>
                  </select>
                  <p className="mt-1 text-xs text-slate-500">
                    {formRecipeType === "production_recipe"
                      ? "ใช้กับครัวกลาง/โรงผลิต เช่น ซอสพื้นฐานหรือวัตถุดิบเตรียม"
                      : "ใช้กับหน้าร้านเพื่อตัดสต็อกจากการขายตามสูตร"}
                  </p>
                </div>
                <div>
                  <Label>Version</Label>
                  <Input type="number" className="mt-1" value={formVersionNo} min="1" step="1" onChange={(e) => setFormVersionNo(e.target.value)} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>วันที่เริ่มใช้</Label>
                  <Input type="date" className="mt-1" value={formEffectiveFrom} onChange={(e) => setFormEffectiveFrom(e.target.value)} />
                </div>
                <div>
                  <Label>วันที่เลิกใช้</Label>
                  <Input type="date" className="mt-1" value={formEffectiveTo} onChange={(e) => setFormEffectiveTo(e.target.value)} />
                </div>
              </div>

              <div className="grid grid-cols-4 gap-4">
                <div>
                  <Label>ราคาขาย</Label>
                  <Input type="number" className="mt-1" value={formSellingPrice} onChange={(e) => setFormSellingPrice(e.target.value)} min="0" step="0.01" />
                </div>
                <div>
                  <Label>ปริมาณที่ได้ต่อครั้ง (yield)</Label>
                  <Input type="number" className="mt-1" value={formYieldQty} onChange={(e) => setFormYieldQty(e.target.value)} min="0.01" step="0.01" />
                </div>
                <div>
                  <Label>หน่วย yield</Label>
                  <Input className="mt-1" value={formYieldUnit} onChange={(e) => setFormYieldUnit(e.target.value)} placeholder="แก้ว / ชิ้น / จาน" />
                </div>
                <div>
                  <Label>Loss %</Label>
                  <Input type="number" className="mt-1" value={formLossPercent} onChange={(e) => setFormLossPercent(e.target.value)} min="0" max="99.99" step="0.01" />
                </div>
              </div>

              {/* Ingredients */}
              <div>
                <div className="flex items-center justify-between">
                  <Label>วัตถุดิบ</Label>
                  <Button variant="outline" size="sm" onClick={addIngredient}>
                    <Plus className="mr-1 h-3 w-3" />
                    เพิ่มวัตถุดิบ
                  </Button>
                </div>
                <div className="mt-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-3">
                  <p className="text-xs font-semibold text-slate-600">สร้างวัตถุดิบใหม่</p>
                  <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-[minmax(180px,1fr)_120px_90px_80px_210px_160px_auto] xl:items-end">
                    <div>
                      <Label className="text-xs">ชื่อวัตถุดิบ</Label>
                      <Input className="mt-1" value={rawName} onChange={(e) => setRawName(e.target.value)} placeholder="เช่น นมสด" />
                    </div>
                    <div>
                      <Label className="text-xs">SKU</Label>
                      <Input className="mt-1" value={rawSku} onChange={(e) => setRawSku(e.target.value)} placeholder="RAW-MILK" />
                    </div>
                    <div>
                      <Label className="text-xs">ต้นทุน/หน่วย</Label>
                      <Input type="number" className="mt-1" value={rawCost} min="0" step="0.0001" onChange={(e) => setRawCost(e.target.value)} />
                    </div>
                    <div>
                      <Label className="text-xs">หน่วย</Label>
                      <Input className="mt-1" value={rawUnit} onChange={(e) => setRawUnit(e.target.value)} placeholder="g/ml" />
                    </div>
                    <div>
                      <Label className="text-xs">แหล่ง stock</Label>
                      <select
                        className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"
                        value={rawInventoryRole}
                        onChange={(e) => setRawInventoryRole(e.target.value as IngredientInventoryRole)}
                      >
                        <option value="central_raw">ส่วนกลางซื้อ/ใช้ผลิต (RAW)</option>
                        <option value="central_ready">ส่วนกลางเตรียมพร้อมส่ง (READY)</option>
                        <option value="store_local">ร้านซื้อเอง (STORE)</option>
                      </select>
                    </div>
                    <div>
                      <Label className="text-xs">รูปวัตถุดิบ</Label>
                      <Input
                        className="mt-1"
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        onChange={(e) => setRawImage(e.target.files?.[0] ?? null)}
                      />
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      disabled={!rawName.trim() || !rawSku.trim() || createRawMaterialMutation.isPending}
                      onClick={() => createRawMaterialMutation.mutate()}
                    >
                      {createRawMaterialMutation.isPending ? "กำลังสร้าง..." : "สร้าง"}
                    </Button>
                  </div>
                </div>
                <div className="mt-3 space-y-2">
                  {formIngredients.length === 0 && (
                    <p className="text-sm text-slate-400">กดปุ่ม "เพิ่มวัตถุดิบ" เพื่อเริ่มต้น</p>
                  )}
                  {formIngredients.map((ing, idx) => (
                    <div key={idx} className="grid grid-cols-[56px_1fr_100px_90px_100px_150px_32px] items-end gap-2">
                      <div>
                        {idx === 0 && <Label className="text-xs">รูป</Label>}
                        <div className="mt-1 flex h-10 w-14 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-white text-[10px] text-slate-400">
                          {ing.image_file ? (
                            <span className="px-1 text-center">รูปใหม่</span>
                          ) : ing.image_url ? (
                            <img src={ing.image_url} alt={ing.ingredient_name || "วัตถุดิบ"} className="h-full w-full object-cover" />
                          ) : (
                            <span>ไม่มี</span>
                          )}
                        </div>
                      </div>
                      <div>
                        {idx === 0 && <Label className="text-xs">วัตถุดิบ (raw_material)</Label>}
                        <select
                          className="mt-1 h-10 w-full rounded-xl border border-slate-300 px-3 text-sm"
                          value={ing.ingredient_id}
                          onChange={(e) => {
                            const p = rawMaterials.find((r) => r.id === e.target.value);
                            updateIngredient(idx, "ingredient_id", e.target.value);
                            if (p) {
                              updateIngredient(idx, "ingredient_name", p.name);
                              updateIngredient(idx, "cost_price", String(p.cost_price ?? 0));
                              updateIngredient(idx, "image_url", p.image_url);
                              updateIngredient(idx, "image_file", null);
                            }
                          }}
                        >
                          <option value="">-- เลือกวัตถุดิบ --</option>
                          {rawMaterials.map((r) => (
                            <option key={r.id} value={r.id}>{r.name}</option>
                          ))}
                        </select>
                        {rawMaterials.length === 0 && idx === 0 && (
                          <p className="text-xs text-amber-600">ยังไม่มีสินค้าประเภท raw_material</p>
                        )}
                      </div>
                      <div>
                        {idx === 0 && <Label className="text-xs">ปริมาณ</Label>}
                        <Input
                          type="number"
                          className="mt-1"
                          value={ing.quantity}
                          onChange={(e) => updateIngredient(idx, "quantity", e.target.value)}
                          min="0.001"
                          step="0.001"
                        />
                      </div>
                      <div>
                        {idx === 0 && <Label className="text-xs">หน่วย</Label>}
                        <Input
                          className="mt-1"
                          value={ing.unit}
                          onChange={(e) => updateIngredient(idx, "unit", e.target.value)}
                          placeholder="g/ml/ชิ้น"
                        />
                      </div>
                      <div>
                        {idx === 0 && <Label className="text-xs">ราคา/หน่วย</Label>}
                        <Input
                          type="number"
                          className="mt-1"
                          value={ing.cost_price}
                          onChange={(e) => updateIngredient(idx, "cost_price", e.target.value)}
                          min="0"
                          step="0.0001"
                        />
                      </div>
                      <div>
                        {idx === 0 && <Label className="text-xs">อัปรูป</Label>}
                        <Input
                          className="mt-1"
                          type="file"
                          accept="image/jpeg,image/png,image/webp"
                          disabled={!ing.ingredient_id}
                          onChange={(e) => updateIngredient(idx, "image_file", e.target.files?.[0] ?? null)}
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => removeIngredient(idx)}
                        className={`flex h-10 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-500 ${idx === 0 ? "mt-6" : "mt-1"}`}
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-4 gap-4 rounded-2xl border border-orange-200 bg-orange-50 p-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-orange-700">Preview ต้นทุนรวม</p>
                  <p className="mt-1 text-2xl font-bold text-slate-950">฿{preview.totalCost.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-orange-700">Yield หลัง loss</p>
                  <p className="mt-1 text-2xl font-bold text-slate-950">
                    {preview.effectiveYield.toFixed(4)} {formYieldUnit}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-orange-700">ต้นทุนต่อ {formYieldUnit || "หน่วย"}</p>
                  <p className="mt-1 text-2xl font-bold text-orange-700">฿{preview.costPerYield.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-orange-700">Gross Margin</p>
                  <p className={`mt-1 text-2xl font-bold ${preview.grossMarginPct >= 40 ? "text-emerald-700" : "text-red-700"}`}>
                    {preview.grossMarginPct.toFixed(1)}%
                  </p>
                </div>
              </div>

              <div>
                <Label>หมายเหตุ (ไม่บังคับ)</Label>
                <textarea
                  className="mt-1 min-h-16 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                  value={formNotes}
                  onChange={(e) => setFormNotes(e.target.value)}
                  placeholder="เช่น ใช้นม oat แทน full cream ได้"
                />
              </div>

              <div className="flex justify-end gap-3">
                <Button variant="outline" onClick={resetForm}>ยกเลิก</Button>
                <Button
                  className="bg-orange-500 hover:bg-orange-600"
                  disabled={!formProductId || !formName || createMutation.isPending || updateMutation.isPending}
                  onClick={() => editingId ? updateMutation.mutate() : createMutation.mutate()}
                >
                  {createMutation.isPending || updateMutation.isPending
                    ? "กำลังบันทึก..."
                    : editingId
                      ? "อัปเดตสูตร"
                      : "บันทึกสูตร"}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
