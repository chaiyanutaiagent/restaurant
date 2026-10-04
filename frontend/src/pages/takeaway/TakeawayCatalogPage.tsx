import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageOff, PackageSearch, Pencil, Plus, Search, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useToast } from "@/components/ui/use-toast";
import {
  takeawayApi,
  type TakeawayCatalogItem,
  type TakeawayCatalogItemPayload,
  type TakeawayCatalogRow,
} from "@/lib/takeawayApi";
import { useAuthStore } from "@/stores/auth.store";

type CatalogMode = "store" | "admin";

type CatalogDraft = Omit<TakeawayCatalogItemPayload, "brand_id">;

const emptyDraft: CatalogDraft = {
  category_id: null,
  sku: "",
  barcode: null,
  name: "",
  description: null,
  image_url: null,
  unit: "ชิ้น",
  price: "0",
  tax_rate: "7",
  kitchen_station: null,
  track_stock: true,
  sort_order: 0,
  is_featured: false,
  is_active: true,
};

const inputClass = "h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100";

function money(value: string | number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(Number(value));
}

function asDraft(item: TakeawayCatalogItem): CatalogDraft {
  return {
    category_id: item.category_id,
    sku: item.sku,
    barcode: item.barcode,
    name: item.name,
    description: item.description,
    image_url: item.image_url,
    unit: item.unit,
    price: String(item.price),
    tax_rate: String(item.tax_rate),
    kitchen_station: item.kitchen_station,
    track_stock: item.track_stock,
    sort_order: item.sort_order,
    is_featured: item.is_featured,
    is_active: item.is_active,
  };
}

export default function TakeawayCatalogPage({ mode = "store" }: { mode?: CatalogMode }): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<CatalogDraft>(emptyDraft);
  const [formOpen, setFormOpen] = useState(false);
  const contextQuery = useQuery({
    queryKey: ["takeaway", "status"],
    queryFn: async () => (await takeawayApi.status()).data.data,
  });
  const context = contextQuery.data;
  const brandId = context?.brand_id ?? null;
  const branchId = mode === "store" ? context?.branch_id ?? null : null;
  const canManage = mode === "admin" && hasPermission("takeaway.catalog.manage");
  const categoriesQuery = useQuery({
    queryKey: ["takeaway", "catalog-categories", brandId],
    queryFn: async () => (await takeawayApi.categories(brandId!)).data.data,
    enabled: Boolean(brandId),
  });
  const catalogQuery = useQuery({
    queryKey: ["takeaway", "catalog", brandId, branchId, mode],
    queryFn: async () => (await takeawayApi.catalog(brandId!, branchId)).data.data,
    enabled: Boolean(brandId),
  });
  const categories = categoriesQuery.data ?? [];
  const categoryNames = useMemo(
    () => new Map(categories.map((category) => [category.id, String(category.name)])),
    [categories],
  );
  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (catalogQuery.data ?? []).filter((row) => {
      if (categoryId && row.item.category_id !== categoryId) return false;
      if (!needle) return true;
      return `${row.item.name} ${row.item.sku} ${row.item.barcode ?? ""} ${row.item.description ?? ""}`
        .toLowerCase()
        .includes(needle);
    });
  }, [catalogQuery.data, categoryId, search]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!brandId) throw new Error("กรุณาเลือกแบรนด์ Takeaway");
      if (!draft.name.trim() || !draft.sku.trim()) throw new Error("กรุณากรอกชื่อและ SKU");
      const payload: CatalogDraft = {
        ...draft,
        name: draft.name.trim(),
        sku: draft.sku.trim(),
        barcode: draft.barcode?.trim() || null,
        description: draft.description?.trim() || null,
        image_url: draft.image_url?.trim() || null,
        unit: draft.unit.trim() || "ชิ้น",
        kitchen_station: draft.kitchen_station?.trim() || null,
      };
      return editingId
        ? takeawayApi.updateCatalogItem(editingId, payload)
        : takeawayApi.createCatalogItem({ ...payload, brand_id: brandId });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["takeaway", "catalog"] });
      setFormOpen(false);
      setEditingId(null);
      setDraft(emptyDraft);
      toast({ title: editingId ? "บันทึกสินค้าแล้ว" : "เพิ่มสินค้าแล้ว" });
    },
    onError: (error) => toast({
      title: "บันทึกสินค้าไม่สำเร็จ",
      description: error instanceof Error ? error.message : "ตรวจข้อมูลแล้วลองใหม่",
      variant: "destructive",
    }),
  });

  function openCreate(): void {
    setEditingId(null);
    setDraft(emptyDraft);
    setFormOpen(true);
  }

  function openEdit(row: TakeawayCatalogRow): void {
    setEditingId(row.item.id);
    setDraft(asDraft(row.item));
    setFormOpen(true);
  }

  if (!contextQuery.isLoading && !brandId) {
    return <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-950">กรุณาเลือกแบรนด์ Takeaway ก่อนเปิดรายการสินค้า</div>;
  }

  return <div className="space-y-5">
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">{mode === "admin" ? "Catalog master" : "Store catalog"}</p>
        <h1 className="mt-1 text-2xl font-black">รายการสินค้า</h1>
        <p className="mt-1 text-sm text-slate-500">รูป ชื่อ ราคา หมวดหมู่ และสถานะพร้อมขายที่หน้าร้านเห็นจริง</p>
      </div>
      {canManage ? <button onClick={openCreate} className="flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-sm font-black text-white"><Plus className="h-4 w-4" /> เพิ่มสินค้า</button> : null}
    </header>

    <section className="space-y-3 rounded-2xl border bg-white p-4 shadow-sm">
      <label className="relative block">
        <Search className="pointer-events-none absolute left-3 top-3 h-5 w-5 text-slate-400" />
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ค้นหาชื่อสินค้า SKU หรือบาร์โค้ด" className="h-11 w-full rounded-xl border pl-10 pr-4 text-sm" />
      </label>
      <div className="flex gap-2 overflow-x-auto">
        <button onClick={() => setCategoryId(null)} className={`min-w-fit rounded-full px-4 py-2 text-sm font-bold ${categoryId === null ? "bg-emerald-500" : "bg-slate-100"}`}>ทั้งหมด</button>
        {categories.map((category) => <button key={category.id} onClick={() => setCategoryId(category.id)} className={`min-w-fit rounded-full px-4 py-2 text-sm font-bold ${categoryId === category.id ? "bg-emerald-500" : "bg-slate-100"}`}>{String(category.name)}</button>)}
      </div>
    </section>

    {catalogQuery.isError ? <section role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-900">
      <h2 className="font-black">โหลดรายการสินค้าไม่สำเร็จ</h2>
      <p className="mt-1 text-sm">ตรวจการเชื่อมต่อหรือการอัปเดตระบบ แล้วลองอีกครั้ง</p>
      <button onClick={() => void catalogQuery.refetch()} className="mt-4 rounded-xl bg-rose-700 px-4 py-2 text-sm font-black text-white">ลองใหม่</button>
    </section> : null}

    {!catalogQuery.isError ? <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {rows.map((row) => {
        const availableQty = row.available_qty == null ? null : Number(row.available_qty);
        return <article key={row.item.id} className={`overflow-hidden rounded-2xl border bg-white shadow-sm ${row.is_available ? "border-slate-200" : "border-rose-200 opacity-75"}`}>
          <div className="relative aspect-[4/3] bg-slate-100">
            {row.item.image_url ? <img src={row.item.image_url} alt={row.item.name} className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center text-slate-400"><ImageOff className="h-10 w-10" /></div>}
            <span className={`absolute right-3 top-3 rounded-full px-3 py-1 text-xs font-black ${row.is_available ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-700"}`}>{row.is_available ? "พร้อมขาย" : "หมด/ปิดขาย"}</span>
            {row.item.is_featured ? <span className="absolute left-3 top-3 rounded-full bg-amber-300 px-3 py-1 text-xs font-black text-amber-950">แนะนำ</span> : null}
          </div>
          <div className="p-4">
            <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-bold text-slate-400">{row.item.sku}{row.item.barcode ? ` · ${row.item.barcode}` : ""}</p><h2 className="mt-1 font-black text-slate-950">{row.item.name}</h2></div><p className="whitespace-nowrap text-lg font-black text-emerald-700">{money(row.effective_price)}</p></div>
            <p className="mt-2 line-clamp-2 min-h-10 text-sm text-slate-500">{row.item.description || "ยังไม่มีรายละเอียดสินค้า"}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-600"><span className="rounded-full bg-slate-100 px-2 py-1">{categoryNames.get(row.item.category_id ?? "") ?? "ไม่ระบุหมวด"}</span><span>{row.item.unit}</span>{availableQty !== null ? <span>พร้อมขาย {availableQty.toLocaleString("th-TH", { maximumFractionDigits: 2 })}</span> : null}</div>
            {canManage ? <button onClick={() => openEdit(row)} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm font-bold"><Pencil className="h-4 w-4" /> แก้ไขสินค้า</button> : null}
          </div>
        </article>;
      })}
      {!catalogQuery.isLoading && rows.length === 0 ? <div className="col-span-full rounded-2xl border border-dashed bg-white p-10 text-center text-slate-500"><PackageSearch className="mx-auto h-10 w-10" /><p className="mt-3 font-bold">ไม่พบสินค้า</p></div> : null}
    </section> : null}

    {formOpen ? <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/55 p-4 backdrop-blur-sm">
      <form onSubmit={(event) => { event.preventDefault(); saveMutation.mutate(); }} className="mx-auto max-w-3xl rounded-3xl bg-white p-5 shadow-2xl md:p-7">
        <div className="flex items-center justify-between"><div><p className="text-xs font-black uppercase tracking-[0.2em] text-emerald-700">Product master</p><h2 className="mt-1 text-2xl font-black">{editingId ? "แก้ไขสินค้า" : "เพิ่มสินค้า"}</h2></div><button type="button" onClick={() => setFormOpen(false)} className="rounded-full bg-slate-100 p-2"><X className="h-5 w-5" /></button></div>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <Field label="ชื่อสินค้า *"><input required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className={inputClass} /></Field>
          <Field label="SKU *"><input required value={draft.sku} onChange={(event) => setDraft({ ...draft, sku: event.target.value })} className={inputClass} /></Field>
          <Field label="บาร์โค้ด"><input value={draft.barcode ?? ""} onChange={(event) => setDraft({ ...draft, barcode: event.target.value || null })} className={inputClass} /></Field>
          <Field label="หมวดหมู่"><select value={draft.category_id ?? ""} onChange={(event) => setDraft({ ...draft, category_id: event.target.value || null })} className={inputClass}><option value="">ไม่ระบุ</option>{categories.map((category) => <option key={category.id} value={category.id}>{String(category.name)}</option>)}</select></Field>
          <Field label="ราคาขาย"><input required type="number" min="0" step="0.01" value={draft.price} onChange={(event) => setDraft({ ...draft, price: event.target.value })} className={inputClass} /></Field>
          <Field label="VAT %"><input type="number" min="0" max="100" step="0.01" value={draft.tax_rate} onChange={(event) => setDraft({ ...draft, tax_rate: event.target.value })} className={inputClass} /></Field>
          <Field label="หน่วย"><input value={draft.unit} onChange={(event) => setDraft({ ...draft, unit: event.target.value })} className={inputClass} /></Field>
          <Field label="จุดเตรียม"><input value={draft.kitchen_station ?? ""} onChange={(event) => setDraft({ ...draft, kitchen_station: event.target.value || null })} className={inputClass} placeholder="เช่น เครื่องดื่ม" /></Field>
          <Field label="URL รูปสินค้า" wide><input type="url" value={draft.image_url ?? ""} onChange={(event) => setDraft({ ...draft, image_url: event.target.value || null })} className={inputClass} placeholder="https://…" /></Field>
          <Field label="รายละเอียดสำหรับลูกค้า" wide><textarea rows={4} value={draft.description ?? ""} onChange={(event) => setDraft({ ...draft, description: event.target.value || null })} className={`${inputClass} min-h-28 py-3`} /></Field>
          <Field label="ลำดับแสดง"><input type="number" min="0" value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} className={inputClass} /></Field>
          <div className="grid gap-2 sm:grid-cols-2 md:col-span-2">
            <Check label="ตัดสต็อก" checked={draft.track_stock} onChange={(checked) => setDraft({ ...draft, track_stock: checked })} />
            <Check label="สินค้าแนะนำ" checked={draft.is_featured} onChange={(checked) => setDraft({ ...draft, is_featured: checked })} />
          </div>
        </div>
        {draft.image_url ? <img src={draft.image_url} alt="ตัวอย่างสินค้า" className="mt-5 aspect-[16/7] w-full rounded-2xl bg-slate-100 object-contain" /> : null}
        <div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setFormOpen(false)} className="rounded-xl border px-5 py-3 font-bold">ยกเลิก</button><button disabled={saveMutation.isPending} type="submit" className="rounded-xl bg-emerald-500 px-5 py-3 font-black text-slate-950 disabled:opacity-50">{saveMutation.isPending ? "กำลังบันทึก…" : "บันทึกสินค้า"}</button></div>
      </form>
    </div> : null}
  </div>;
}

function Field({ label, wide = false, children }: { label: string; wide?: boolean; children: ReactNode }): JSX.Element {
  return <label className={`text-sm font-bold text-slate-700 ${wide ? "md:col-span-2" : ""}`}>{label}<div className="mt-1">{children}</div></label>;
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }): JSX.Element {
  return <label className="flex items-center gap-3 rounded-xl border p-3 text-sm font-bold"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="h-5 w-5" />{label}</label>;
}
