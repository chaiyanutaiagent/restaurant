import {
  ChefHat,
  Minus,
  Plus,
  Search,
  ShoppingCart,
  Trash2,
  Utensils,
  WifiOff,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { SystemState } from "@/components/ui/system-state";
import { PLATFORM_BRAND } from "@/config/platformBrand";
import { formatThaiCurrency } from "@/lib/cartUtils";
import { DEFAULT_MODIFIER_OPTIONS } from "@/pages/restaurant/components/MobileOrdering";

export type StaffMenuProduct = {
  id: string;
  name: string;
  selling_price: string | number;
  image_url: string | null;
  category_id: string | null;
  category_name?: string | null;
  description?: string | null;
  is_available?: boolean;
};

export type StaffOrderCartLine = {
  line_id: string;
  product: StaffMenuProduct;
  qty: number;
  special_request: string;
};

type MenuCategory = {
  id: string;
  name: string;
};

type RestaurantOrderComposerProps = {
  open: boolean;
  title: string;
  subtitle?: string;
  products: StaffMenuProduct[];
  categories: MenuCategory[];
  cart: StaffOrderCartLine[];
  isLoading: boolean;
  isError: boolean;
  isSubmitting: boolean;
  isOnline: boolean;
  onRetry: () => void;
  onClose: () => void;
  onAdd: (product: StaffMenuProduct, specialRequest?: string) => void;
  onQuantityChange: (lineId: string, delta: number) => void;
  onRemove: (lineId: string) => void;
  onSubmit: () => void;
};

function normalizeCategory(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLocaleLowerCase("th-TH");
}

export default function RestaurantOrderComposer({
  open,
  title,
  subtitle,
  products,
  categories,
  cart,
  isLoading,
  isError,
  isSubmitting,
  isOnline,
  onRetry,
  onClose,
  onAdd,
  onQuantityChange,
  onRemove,
  onSubmit,
}: RestaurantOrderComposerProps): JSX.Element | null {
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [customProduct, setCustomProduct] = useState<StaffMenuProduct | null>(null);
  const [customOptions, setCustomOptions] = useState<string[]>([]);
  const [customNote, setCustomNote] = useState("");

  useEffect(() => {
    if (!open) return;
    setSearch("");
    setSelectedCategory("");
    setCustomProduct(null);
    setCustomOptions([]);
    setCustomNote("");
  }, [open]);

  const categoryGroups = useMemo(() => {
    const productCategoryIds = new Set(products.map((product) => product.category_id).filter(Boolean));
    const groups = new Map<string, { key: string; name: string; ids: Set<string> }>();
    for (const category of categories) {
      if (!productCategoryIds.has(category.id)) continue;
      const key = normalizeCategory(category.name);
      const group = groups.get(key) ?? { key, name: category.name.trim(), ids: new Set<string>() };
      group.ids.add(category.id);
      groups.set(key, group);
    }
    return [...groups.values()].sort((left, right) => left.name.localeCompare(right.name, "th"));
  }, [categories, products]);

  const visibleProducts = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("th-TH");
    const category = categoryGroups.find((entry) => entry.key === selectedCategory);
    return products.filter((product) => {
      if (product.is_available === false) return false;
      if (category && (!product.category_id || !category.ids.has(product.category_id))) return false;
      if (!query) return true;
      return `${product.name} ${product.category_name ?? ""} ${product.description ?? ""}`
        .toLocaleLowerCase("th-TH")
        .includes(query);
    });
  }, [categoryGroups, products, search, selectedCategory]);

  const totalQty = cart.reduce((sum, line) => sum + line.qty, 0);
  const totalAmount = cart.reduce(
    (sum, line) => sum + Number(line.product.selling_price) * line.qty,
    0,
  );

  function openOptions(product: StaffMenuProduct): void {
    setCustomProduct(product);
    setCustomOptions([]);
    setCustomNote("");
  }

  function submitOptions(): void {
    if (!customProduct) return;
    const specialRequest = [...customOptions, customNote.trim()].filter(Boolean).join(", ");
    onAdd(customProduct, specialRequest);
    setCustomProduct(null);
    setCustomOptions([]);
    setCustomNote("");
  }

  if (!open) return null;

  return (
    <div
      data-pos-touch-surface
      data-testid="restaurant-order-composer"
      className="fixed inset-0 z-[80] flex min-h-0 flex-col bg-[linear-gradient(180deg,#f8fbff_0%,#eef4ff_100%)] text-slate-950"
    >
      <header className="flex min-h-[68px] shrink-0 items-center gap-3 border-b border-blue-100 bg-white px-4 shadow-sm lg:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-blue-600 text-lg font-black text-white shadow-sm" aria-hidden="true">
            F
          </span>
          <div className="hidden min-w-0 sm:block">
            <p className="truncate text-base font-black text-blue-700">{PLATFORM_BRAND.productName}</p>
            <p className="text-xs text-slate-500">Restaurant POS</p>
          </div>
          <span className="hidden h-8 w-px bg-slate-200 lg:block" aria-hidden="true" />
          <div className="min-w-0">
            <h1 className="truncate text-lg font-black lg:text-xl">{title}</h1>
            {subtitle ? <p className="truncate text-xs text-slate-500">{subtitle}</p> : null}
          </div>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <span className={`hidden min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-bold md:inline-flex ${isOnline ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>
            {isOnline ? <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> : <WifiOff className="h-4 w-4" />}
            {isOnline ? "ออนไลน์" : "ออฟไลน์"}
          </span>
          <Button variant="outline" className="h-11 rounded-xl px-4" onClick={onClose} disabled={isSubmitting}>
            <X className="h-5 w-5" /> ปิด
          </Button>
        </div>
      </header>

      {!isOnline ? (
        <div role="alert" className="flex min-h-11 shrink-0 items-center justify-center gap-2 border-b border-amber-200 bg-amber-50 px-4 text-sm font-bold text-amber-900">
          <WifiOff className="h-4 w-4" /> ออฟไลน์ — ดูเมนูได้ แต่ต้องเชื่อมต่อก่อนส่งออเดอร์เข้าครัว
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <nav aria-label="หมวดเมนู" className="w-28 shrink-0 overflow-y-auto border-r border-blue-100 bg-white p-2 lg:w-40 lg:p-3">
          <p className="hidden px-2 pb-3 text-xs font-bold uppercase tracking-[0.18em] text-slate-400 lg:block">หมวดเมนู</p>
          <div className="space-y-2">
            <button
              type="button"
              aria-pressed={!selectedCategory}
              onClick={() => setSelectedCategory("")}
              className={`flex min-h-16 w-full flex-col items-center justify-center rounded-2xl px-2 text-center text-sm font-black ${!selectedCategory ? "bg-blue-600 text-white shadow-md" : "border border-slate-200 bg-white text-slate-700"}`}
            >
              <Utensils className="mb-1 h-5 w-5" /> ทั้งหมด
            </button>
            {categoryGroups.map((category) => (
              <button
                key={category.key}
                type="button"
                aria-pressed={selectedCategory === category.key}
                onClick={() => setSelectedCategory(category.key)}
                className={`min-h-14 w-full rounded-2xl px-2 py-2 text-center text-sm font-bold ${selectedCategory === category.key ? "bg-blue-600 text-white shadow-md" : "border border-slate-200 bg-white text-slate-700"}`}
              >
                {category.name}
              </button>
            ))}
          </div>
        </nav>

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden p-3 lg:p-4">
          <label className="relative block shrink-0">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            <input
              className="h-12 w-full rounded-2xl border border-slate-200 bg-white pl-12 pr-12 text-base shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="ค้นหาเมนู"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              autoFocus
            />
            {search ? (
              <button type="button" aria-label="ล้างคำค้นหา" onClick={() => setSearch("")} className="absolute right-1 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-xl text-slate-500">
                <X className="h-5 w-5" />
              </button>
            ) : null}
          </label>

          <div className="mt-3 flex items-center justify-between text-sm">
            <p className="font-bold text-slate-700">{visibleProducts.length} เมนู</p>
            <p className="text-slate-500">แตะ + เพื่อเพิ่มทันที หรือเลือกตัวเลือกก่อนส่งครัว</p>
          </div>

          <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
            {isLoading ? <SystemState kind="loading" title="กำลังโหลดเมนูร้านอาหาร" /> : null}
            {isError ? (
              <SystemState kind="error" title="โหลดเมนูร้านอาหารไม่สำเร็จ" description="คำสั่งส่งครัวถูกปิดไว้จนกว่าจะโหลดข้อมูลจาก Server ได้" onAction={onRetry} />
            ) : null}
            {!isLoading && !isError && visibleProducts.length === 0 ? (
              <SystemState kind={search || selectedCategory ? "no_results" : "empty"} title={search || selectedCategory ? "ไม่พบเมนูที่ตรงกัน" : "ยังไม่มีเมนูพร้อมขาย"} />
            ) : null}
            {!isLoading && !isError && visibleProducts.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {visibleProducts.map((product) => (
                  <article key={product.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    {product.image_url ? (
                      <img src={product.image_url} alt={product.name} className="aspect-[16/8] w-full object-cover" loading="lazy" />
                    ) : (
                      <div className="flex aspect-[16/7] w-full items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 text-blue-500">
                        <Utensils className="h-10 w-10" />
                      </div>
                    )}
                    <div className="p-3">
                      <div className="flex min-h-[54px] items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h2 className="line-clamp-2 text-base font-black leading-6">{product.name}</h2>
                          {product.category_name ? <p className="mt-1 text-xs text-slate-500">{product.category_name}</p> : null}
                        </div>
                        <p className="shrink-0 text-base font-black text-blue-700">{formatThaiCurrency(Number(product.selling_price))}</p>
                      </div>
                      <div className="mt-3 grid grid-cols-[1fr_64px] gap-2">
                        <button type="button" onClick={() => openOptions(product)} className="min-h-12 rounded-xl border border-blue-200 bg-blue-50 px-3 text-sm font-bold text-blue-800">
                          ตัวเลือก
                        </button>
                        <button type="button" aria-label={`เพิ่ม ${product.name}`} onClick={() => onAdd(product)} className="flex min-h-12 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm hover:bg-blue-700">
                          <Plus className="h-6 w-6" />
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </div>
        </main>

        <aside aria-label="ตะกร้าออเดอร์" className="flex w-[340px] shrink-0 flex-col border-l border-blue-100 bg-white xl:w-[400px]">
          <div className="flex min-h-[64px] shrink-0 items-center justify-between border-b border-slate-200 px-4">
            <div>
              <h2 className="text-lg font-black">ออเดอร์</h2>
              <p className="text-xs text-slate-500">{totalQty} รายการ</p>
            </div>
            {cart.length > 0 ? <span className="rounded-full bg-blue-100 px-3 py-1 text-sm font-black text-blue-700">{cart.length} บรรทัด</span> : null}
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3 lg:p-4">
            {cart.length === 0 ? (
              <SystemState compact kind="empty" title="ยังไม่มีรายการในออเดอร์" description="เลือกเมนูจากตรงกลางเพื่อเริ่มสั่ง" />
            ) : null}
            {cart.map((line) => (
              <article key={line.line_id} className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
                <div className="flex items-start gap-3">
                  {line.product.image_url ? (
                    <img src={line.product.image_url} alt="" className="h-14 w-14 shrink-0 rounded-xl object-cover" />
                  ) : (
                    <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-500"><Utensils className="h-5 w-5" /></span>
                  )}
                  <div className="min-w-0 flex-1">
                    <h3 className="line-clamp-2 font-black leading-5">{line.product.name}</h3>
                    {line.special_request ? <p className="mt-1 rounded-lg bg-amber-50 px-2 py-1 text-xs font-bold text-amber-800">{line.special_request}</p> : null}
                  </div>
                  <button type="button" aria-label={`ลบ ${line.product.name}`} onClick={() => onRemove(line.line_id)} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-red-600 hover:bg-red-50">
                    <Trash2 className="h-5 w-5" />
                  </button>
                </div>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <button type="button" aria-label={`ลดจำนวน ${line.product.name}`} onClick={() => onQuantityChange(line.line_id, -1)} className="flex h-11 w-11 items-center justify-center rounded-xl border border-slate-200 text-slate-700">
                      <Minus className="h-5 w-5" />
                    </button>
                    <span className="w-10 text-center text-lg font-black">{line.qty}</span>
                    <button type="button" aria-label={`เพิ่มจำนวน ${line.product.name}`} onClick={() => onQuantityChange(line.line_id, 1)} className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
                      <Plus className="h-5 w-5" />
                    </button>
                  </div>
                  <p className="text-base font-black text-blue-800">{formatThaiCurrency(Number(line.product.selling_price) * line.qty)}</p>
                </div>
              </article>
            ))}
          </div>

          <div className="shrink-0 border-t border-slate-200 bg-white p-4 shadow-[0_-8px_24px_rgba(15,23,42,0.06)]">
            <div className="mb-3 flex items-end justify-between">
              <div>
                <p className="text-sm font-bold text-slate-600">รวม</p>
                <p className="text-xs text-slate-400">Server จะตรวจราคาอีกครั้งก่อนรับออเดอร์</p>
              </div>
              <p className="text-2xl font-black text-slate-950">{formatThaiCurrency(totalAmount)}</p>
            </div>
            <Button
              className="h-16 w-full rounded-2xl bg-emerald-600 text-lg font-black text-white shadow-lg hover:bg-emerald-700"
              disabled={cart.length === 0 || isSubmitting || isError || !isOnline}
              onClick={onSubmit}
            >
              {isSubmitting ? "กำลังส่งเข้าครัว…" : <><ChefHat className="h-6 w-6" /> ส่งครัว · {formatThaiCurrency(totalAmount)}</>}
            </Button>
          </div>
        </aside>
      </div>

      {customProduct ? (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm" role="presentation">
          <section role="dialog" aria-modal="true" aria-labelledby="staff-modifier-title" className="flex max-h-[90dvh] w-full max-w-xl flex-col overflow-hidden rounded-[28px] bg-white shadow-2xl">
            <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
              <div>
                <h2 id="staff-modifier-title" className="text-xl font-black">{customProduct.name}</h2>
                <p className="mt-1 font-black text-blue-700">{formatThaiCurrency(Number(customProduct.selling_price))}</p>
              </div>
              <button type="button" aria-label="ปิดตัวเลือก" onClick={() => setCustomProduct(null)} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-700">
                <X className="h-5 w-5" />
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto p-5">
              <p className="text-sm font-black text-slate-800">ตัวเลือกเร็ว</p>
              <p className="mt-1 text-xs text-slate-500">ตัวเลือกชุดนี้บันทึกเป็นหมายเหตุ ยังไม่คิดราคาเพิ่มหรือลด</p>
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {DEFAULT_MODIFIER_OPTIONS.map((option) => {
                  const selected = customOptions.includes(option);
                  return (
                    <button
                      key={option}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => setCustomOptions((current) => selected ? current.filter((item) => item !== option) : [...current, option])}
                      className={`min-h-12 rounded-xl border px-3 py-2 text-sm font-bold ${selected ? "border-blue-600 bg-blue-600 text-white" : "border-slate-200 bg-white text-slate-700"}`}
                    >
                      {option}
                    </button>
                  );
                })}
              </div>
              <label className="mt-5 block text-sm font-black text-slate-800" htmlFor="staff-order-note">หมายเหตุเพิ่มเติม</label>
              <textarea
                id="staff-order-note"
                rows={4}
                maxLength={500}
                className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-base outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                placeholder="เช่น แยกซอส ไม่ใส่หอม"
                value={customNote}
                onChange={(event) => setCustomNote(event.target.value)}
              />
            </div>
            <footer className="grid grid-cols-[120px_1fr] gap-3 border-t border-slate-200 p-4">
              <Button variant="outline" className="h-14 rounded-xl" onClick={() => setCustomProduct(null)}>ยกเลิก</Button>
              <Button className="h-14 rounded-xl bg-blue-600 text-base font-black hover:bg-blue-700" onClick={submitOptions}>
                <ShoppingCart className="h-5 w-5" /> เพิ่มลงออเดอร์
              </Button>
            </footer>
          </section>
        </div>
      ) : null}
    </div>
  );
}
