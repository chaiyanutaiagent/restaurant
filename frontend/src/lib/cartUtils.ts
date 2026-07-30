import type { ProductListItem } from "@/types/product";
import type { Cart, CartItem } from "@/types/pos";

function round2(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function calcItemVat(subtotal: number, vatType: string, vatRate: number): number {
  if (vatType === "included") {
    return round2((subtotal * vatRate) / (100 + vatRate));
  }
  if (vatType === "excluded") {
    return round2((subtotal * vatRate) / 100);
  }
  return 0;
}

export function buildCartItem(
  product: ProductListItem,
  qty: number,
  overridePrice?: number,
): CartItem {
  const originalPrice = Number(overridePrice ?? product.selling_price ?? 0);
  const vatRate = Number(product.vat_rate ?? 7);
  const subtotal = round2(qty * originalPrice);
  return {
    product_id: product.id,
    variant_id: null,
    product_name: product.name,
    variant_name: null,
    sku: product.sku,
    unit_code: null,
    qty,
    unit_price: originalPrice,
    original_price: originalPrice,
    discount_amount: 0,
    discount_type: "amount",
    vat_type: product.vat_type,
    vat_rate: vatRate,
    subtotal,
    vat_amount: calcItemVat(subtotal, product.vat_type, vatRate),
  };
}

function calcDiscount(base: number, discountAmount: number, discountType: string): number {
  if (discountType === "percent") {
    return round2((base * discountAmount) / 100);
  }
  return round2(discountAmount);
}

export function calcCart(items: CartItem[], orderDiscount: number, discountType: string): Cart {
  const normalizedItems = items.map((item) => {
    const itemDiscount = calcDiscount(item.original_price, item.discount_amount, item.discount_type);
    const effectivePrice = Math.max(0, round2(item.original_price - itemDiscount));
    const subtotal = round2(effectivePrice * item.qty);
    const vatAmount = calcItemVat(subtotal, item.vat_type, item.vat_rate);
    return {
      ...item,
      unit_price: effectivePrice,
      subtotal,
      vat_amount: vatAmount,
    };
  });

  const subtotal = round2(normalizedItems.reduce((sum, item) => sum + item.subtotal, 0));
  const orderDiscountValue = calcDiscount(subtotal, orderDiscount, discountType);
  const excludedVat = round2(
    normalizedItems
      .filter((item) => item.vat_type === "excluded")
      .reduce((sum, item) => sum + item.vat_amount, 0),
  );
  const vatAmount = round2(normalizedItems.reduce((sum, item) => sum + item.vat_amount, 0));
  const totalAmount = round2(subtotal - orderDiscountValue + excludedVat);

  return {
    items: normalizedItems,
    discount_amount: orderDiscount,
    discount_type: discountType as "amount" | "percent",
    subtotal,
    order_discount: orderDiscountValue,
    vat_amount: vatAmount,
    total_amount: totalAmount,
  };
}

export function calcChange(totalAmount: number, paidAmount: number): number {
  return round2(Math.max(0, paidAmount - totalAmount));
}

export function formatThaiCurrency(amount: number): string {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    minimumFractionDigits: 2,
  }).format(amount);
}

export function formatThaiDate(isoString: string): string {
  const dt = new Date(isoString);
  const year = dt.getFullYear() + 543;
  const month = `${dt.getMonth() + 1}`.padStart(2, "0");
  const day = `${dt.getDate()}`.padStart(2, "0");
  const hours = `${dt.getHours()}`.padStart(2, "0");
  const minutes = `${dt.getMinutes()}`.padStart(2, "0");
  return `${day}/${month}/${year} ${hours}:${minutes}`;
}

export function generateClientOrderId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `offline-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
