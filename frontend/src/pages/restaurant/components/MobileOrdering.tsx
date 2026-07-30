import { ChevronRight, Minus, Plus, Search, ShoppingCart, Trash2, Utensils, X } from "lucide-react";
import type { ReactNode } from "react";

export type MobileMenuItem = {
  id: string;
  name: string;
  description: string | null;
  selling_price: number;
  category_id: string | null;
  category_name: string | null;
  image_url: string | null;
  is_available: boolean;
};

export type MobileCategory = { id: string; name: string };

export type MobileCartItem<TProduct extends MobileMenuItem = MobileMenuItem> = {
  product: TProduct;
  qty: number;
  special_request: string;
};

export function formatCurrency(value: number): string {
  return `฿${value.toFixed(0)}`;
}

export function filterMenuProducts<TProduct extends MobileMenuItem>(
  products: TProduct[],
  categoryId: string,
  searchTerm: string
): TProduct[] {
  const normalized = searchTerm.trim().toLowerCase();
  return products.filter((product) => {
    const categoryMatched = !categoryId || product.category_id === categoryId;
    if (!categoryMatched) return false;
    if (!normalized) return true;
    return `${product.name} ${product.description ?? ""} ${product.category_name ?? ""}`.toLowerCase().includes(normalized);
  });
}

type MenuSearchProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

export function MenuSearch({ value, onChange, placeholder = "ค้นหาเมนู" }: MenuSearchProps): JSX.Element {
  return (
    <div className="px-4 pt-4">
      <label className="relative block">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          className="h-11 w-full rounded-2xl border border-slate-200 bg-white pl-10 pr-10 text-sm outline-none shadow-sm placeholder:text-slate-400 focus:border-slate-400"
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        {value ? (
          <button
            type="button"
            aria-label="ล้างคำค้นหา"
            onClick={() => onChange("")}
            className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full bg-slate-100 text-slate-500"
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}
      </label>
    </div>
  );
}

type CategoryTabsProps = {
  categories: MobileCategory[];
  selectedCategory: string;
  onSelect: (categoryId: string) => void;
  stickyTopClassName?: string;
};

export function CategoryTabs({ categories, selectedCategory, onSelect, stickyTopClassName = "top-[94px]" }: CategoryTabsProps): JSX.Element {
  return (
    <div className={`sticky ${stickyTopClassName} z-10 mt-4 border-y border-slate-200 bg-slate-50/95 px-4 py-3 backdrop-blur`}>
      <div className="flex gap-2 overflow-x-auto">
        <button
          type="button"
          onClick={() => onSelect("")}
          className={`h-10 flex-shrink-0 rounded-full px-4 text-sm font-semibold transition-all ${!selectedCategory ? "bg-slate-950 text-white shadow-sm" : "border border-slate-200 bg-white text-slate-600"}`}
        >
          ทั้งหมด
        </button>
        {categories.map((category) => (
          <button
            key={category.id}
            type="button"
            onClick={() => onSelect(category.id)}
            className={`h-10 flex-shrink-0 rounded-full px-4 text-sm font-semibold transition-all ${selectedCategory === category.id ? "bg-slate-950 text-white shadow-sm" : "border border-slate-200 bg-white text-slate-600"}`}
          >
            {category.name}
          </button>
        ))}
      </div>
    </div>
  );
}

type QuantityControlProps = {
  label: string;
  qty: number;
  onDecrease: () => void;
  onIncrease: () => void;
};

export function QuantityControl({ label, qty, onDecrease, onIncrease }: QuantityControlProps): JSX.Element {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 p-1">
      <button type="button" aria-label={`ลดจำนวน ${label}`} onClick={onDecrease} className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-slate-700 shadow-sm">
        <Minus className="h-4 w-4" />
      </button>
      <span className="w-7 text-center font-bold text-slate-950">{qty}</span>
      <button type="button" aria-label={`เพิ่มจำนวน ${label}`} onClick={onIncrease} className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-950 text-white shadow-sm">
        <Plus className="h-4 w-4" />
      </button>
    </div>
  );
}

type MenuItemRowProps<TProduct extends MobileMenuItem> = {
  product: TProduct;
  cartItem?: MobileCartItem<TProduct>;
  onAdd: (product: TProduct) => void;
  onCustomize?: (product: TProduct) => void;
  onQtyChange: (productId: string, delta: number) => void;
};

export function MenuItemRow<TProduct extends MobileMenuItem>({ product, cartItem, onAdd, onCustomize, onQtyChange }: MenuItemRowProps<TProduct>): JSX.Element {
  return (
    <div className={`flex items-stretch gap-3 rounded-2xl border bg-white p-3 shadow-sm ${product.is_available ? "border-slate-200" : "border-slate-200 opacity-65"}`}>
      {product.image_url ? (
        <img src={product.image_url} alt={product.name} className="h-16 w-16 flex-shrink-0 rounded-xl object-cover min-[380px]:h-20 min-[380px]:w-20" />
      ) : (
        <div className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-500 min-[380px]:h-20 min-[380px]:w-20">
          <Utensils className="h-6 w-6 min-[380px]:h-7 min-[380px]:w-7" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 font-semibold leading-snug text-slate-950">{product.name}</p>
        {product.description ? <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-500">{product.description}</p> : null}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-base font-bold text-emerald-700">{formatCurrency(Number(product.selling_price))}</p>
            {!product.is_available ? <p className="mt-0.5 text-xs font-semibold text-red-600">หมดชั่วคราว</p> : null}
          </div>
          {cartItem ? (
            <QuantityControl
              label={product.name}
              qty={cartItem.qty}
              onDecrease={() => onQtyChange(product.id, -1)}
              onIncrease={() => onQtyChange(product.id, 1)}
            />
          ) : (
            <div className="flex items-center gap-2">
              {onCustomize ? (
                <button
                  type="button"
                  disabled={!product.is_available}
                  onClick={() => onCustomize(product)}
                  className="h-9 rounded-full border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 shadow-sm disabled:text-slate-400 min-[380px]:h-10 min-[380px]:text-sm"
                >
                  ตัวเลือก
                </button>
              ) : null}
              <button
                type="button"
                disabled={!product.is_available}
                onClick={() => onAdd(product)}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-slate-950 px-3 text-xs font-semibold text-white shadow-sm disabled:bg-slate-200 disabled:text-slate-500 min-[380px]:h-10 min-[380px]:text-sm"
              >
                {product.is_available ? "เพิ่ม" : "หมด"}
                {product.is_available ? <Plus className="h-4 w-4" /> : null}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

type MenuListProps<TProduct extends MobileMenuItem> = {
  products: TProduct[];
  cart: MobileCartItem<TProduct>[];
  onAdd: (product: TProduct) => void;
  onQtyChange: (productId: string, delta: number) => void;
  onCustomize?: (product: TProduct) => void;
  emptyLabel?: string;
};

export function MenuList<TProduct extends MobileMenuItem>({ products, cart, onAdd, onQtyChange, onCustomize, emptyLabel = "ยังไม่มีเมนูในหมวดนี้" }: MenuListProps<TProduct>): JSX.Element {
  return (
    <div className="space-y-3 px-4 py-4">
      {products.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-slate-500">
          <Utensils className="mx-auto mb-2 h-7 w-7 text-slate-400" />
          <p className="font-medium">{emptyLabel}</p>
        </div>
      ) : null}
      {products.map((product) => (
        <MenuItemRow
          key={product.id}
          product={product}
          cartItem={cart.find((item) => item.product.id === product.id)}
          onAdd={onAdd}
          onQtyChange={onQtyChange}
          onCustomize={onCustomize}
        />
      ))}
    </div>
  );
}

export const DEFAULT_MODIFIER_OPTIONS = [
  "ไม่หวาน",
  "หวานน้อย",
  "หวานปกติ",
  "เพิ่มช็อต",
  "ไม่ใส่น้ำแข็ง",
  "แยกน้ำแข็ง",
  "ไม่ใส่ผัก",
  "เผ็ดน้อย"
];

type ItemDetailSheetProps<TProduct extends MobileMenuItem> = {
  product: TProduct | null;
  note: string;
  selectedOptions: string[];
  options?: string[];
  onNoteChange: (value: string) => void;
  onToggleOption: (option: string) => void;
  onClose: () => void;
  onSubmit: () => void;
};

export function ItemDetailSheet<TProduct extends MobileMenuItem>({
  product,
  note,
  selectedOptions,
  options = DEFAULT_MODIFIER_OPTIONS,
  onNoteChange,
  onToggleOption,
  onClose,
  onSubmit
}: ItemDetailSheetProps<TProduct>): JSX.Element | null {
  if (!product) return null;

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-white">
      <div className="mx-auto flex w-full max-w-lg items-center justify-between border-b px-4 py-4">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-bold text-slate-950">{product.name}</h2>
          <p className="text-sm font-semibold text-emerald-700">{formatCurrency(Number(product.selling_price))}</p>
        </div>
        <button type="button" aria-label="ปิดตัวเลือก" onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-700">
          <X className="h-5 w-5" />
        </button>
      </div>
      <div className="mx-auto w-full max-w-lg flex-1 overflow-y-auto px-4 py-4">
        {product.image_url ? (
          <img src={product.image_url} alt={product.name} className="mb-4 aspect-[16/9] w-full rounded-2xl object-cover" />
        ) : null}
        {product.description ? <p className="mb-4 text-sm leading-relaxed text-slate-600">{product.description}</p> : null}
        <p className="mb-2 text-sm font-semibold text-slate-900">ตัวเลือกเร็ว</p>
        <div className="flex flex-wrap gap-2">
          {options.map((option) => {
            const selected = selectedOptions.includes(option);
            return (
              <button
                key={option}
                type="button"
                onClick={() => onToggleOption(option)}
                className={`rounded-full px-3 py-2 text-sm font-semibold ${selected ? "bg-slate-950 text-white" : "border border-slate-200 bg-white text-slate-700"}`}
              >
                {option}
              </button>
            );
          })}
        </div>
        <textarea
          className="mt-4 w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
          placeholder="หมายเหตุเพิ่มเติม เช่น แยกซอส ไม่ใส่หอม"
          value={note}
          rows={4}
          onChange={(event) => onNoteChange(event.target.value)}
        />
      </div>
      <div className="border-t px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-4">
        <div className="mx-auto max-w-lg">
          <button type="button" onClick={onSubmit} className="h-14 w-full rounded-2xl bg-slate-950 text-lg font-bold text-white shadow-sm">
            เพิ่มลงตะกร้า
          </button>
        </div>
      </div>
    </div>
  );
}

type CartBarProps = {
  count: number;
  total: number;
  onOpen: () => void;
};

export function CartBar({ count, total, onOpen }: CartBarProps): JSX.Element | null {
  if (count <= 0) return null;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="fixed bottom-[calc(1rem+env(safe-area-inset-bottom))] left-4 right-4 z-20 mx-auto flex max-w-lg items-center justify-between rounded-2xl bg-slate-950 px-4 py-4 text-white shadow-xl"
    >
      <span className="inline-flex items-center gap-2 font-semibold">
        <ShoppingCart className="h-5 w-5" />
        {count} รายการ
      </span>
      <span className="inline-flex items-center gap-2 font-bold">
        {formatCurrency(total)}
        <ChevronRight className="h-5 w-5" />
      </span>
    </button>
  );
}

type CartSheetProps<TProduct extends MobileMenuItem> = {
  open: boolean;
  title: string;
  subtitle: string;
  cart: MobileCartItem<TProduct>[];
  note: string;
  notePlaceholder: string;
  submitLabel: string;
  isSubmitting: boolean;
  extraFields?: ReactNode;
  onClose: () => void;
  onRemove: (productId: string) => void;
  onQtyChange: (productId: string, delta: number) => void;
  onItemNoteChange: (productId: string, value: string) => void;
  onNoteChange: (value: string) => void;
  onSubmit: () => void;
};

export function CartSheet<TProduct extends MobileMenuItem>({
  open,
  title,
  subtitle,
  cart,
  note,
  notePlaceholder,
  submitLabel,
  isSubmitting,
  extraFields,
  onClose,
  onRemove,
  onQtyChange,
  onItemNoteChange,
  onNoteChange,
  onSubmit
}: CartSheetProps<TProduct>): JSX.Element | null {
  if (!open) return null;

  const total = cart.reduce((sum, item) => sum + item.product.selling_price * item.qty, 0);
  const cartCount = cart.reduce((sum, item) => sum + item.qty, 0);

  return (
    <div className="fixed inset-0 z-30 flex flex-col bg-white">
      <div className="mx-auto flex w-full max-w-lg items-center justify-between border-b px-4 py-4">
        <div>
          <h2 className="text-lg font-bold text-slate-950">{title}</h2>
          <p className="text-sm text-slate-500">{cartCount > 0 ? subtitle : "ยังไม่มีรายการในตะกร้า"}</p>
        </div>
        <button type="button" aria-label="ปิดตะกร้า" onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-700">
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="mx-auto w-full max-w-lg flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {extraFields}
        {cart.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-10 text-center">
            <ShoppingCart className="mx-auto mb-3 h-8 w-8 text-slate-400" />
            <p className="font-semibold text-slate-800">ตะกร้าว่างอยู่</p>
            <p className="mt-1 text-sm text-slate-500">กลับไปเลือกเมนู แล้วค่อยส่งออเดอร์</p>
          </div>
        ) : null}
        {cart.map((item) => (
          <div key={item.product.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <p className="font-semibold text-slate-950">{item.product.name}</p>
              <button type="button" aria-label={`ลบ ${item.product.name}`} onClick={() => onRemove(item.product.id)} className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <QuantityControl
                label={item.product.name}
                qty={item.qty}
                onDecrease={() => onQtyChange(item.product.id, -1)}
                onIncrease={() => onQtyChange(item.product.id, 1)}
              />
              <span className="font-bold text-emerald-700">{formatCurrency(item.product.selling_price * item.qty)}</span>
            </div>
            <input
              className="mt-3 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
              placeholder="หมายเหตุรายเมนู เช่น ไม่ใส่น้ำตาล"
              value={item.special_request}
              onChange={(event) => onItemNoteChange(item.product.id, event.target.value)}
            />
          </div>
        ))}
        <textarea
          className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
          placeholder={notePlaceholder}
          value={note}
          rows={2}
          onChange={(event) => onNoteChange(event.target.value)}
        />
      </div>

      <div className="border-t bg-white px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-4">
        <div className="mx-auto max-w-lg">
          <div className="mb-3 flex justify-between text-lg font-bold">
            <span>รวม</span>
            <span className="text-emerald-700">{formatCurrency(total)}</span>
          </div>
          <button
            type="button"
            disabled={isSubmitting || cart.length === 0}
            onClick={onSubmit}
            className="h-14 w-full rounded-2xl bg-slate-950 text-lg font-bold text-white shadow-sm disabled:opacity-60"
          >
            {isSubmitting ? "กำลังส่ง..." : submitLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

type StatusListProps = {
  items: { id: string; product_name: string; qty: number; status: string; special_request?: string | null }[];
  labels: Record<string, { label: string; color: string }>;
};

export function StatusList({ items, labels }: StatusListProps): JSX.Element {
  return (
    <div className="mt-4 space-y-2">
      {items.map((item) => (
        <div key={item.id} className="rounded-xl bg-white/80 px-3 py-2 text-sm">
          <div className="flex items-center justify-between gap-3">
            <span className="min-w-0 flex-1 truncate font-medium text-slate-700">{item.product_name} x{item.qty}</span>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${labels[item.status]?.color ?? "bg-slate-100 text-slate-600"}`}>
              {labels[item.status]?.label ?? item.status}
            </span>
          </div>
          {item.special_request ? (
            <p className="mt-1 truncate text-xs text-slate-500">หมายเหตุ: {item.special_request}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}
