const aliases: Record<string, string> = {
  กรัม: 'g', ก: 'g', gram: 'g', grams: 'g', กก: 'kg', กิโล: 'kg', กิโลกรัม: 'kg', kilogram: 'kg', kilograms: 'kg',
  มล: 'ml', มิลลิลิตร: 'ml', milliliter: 'ml', milliliters: 'ml', ลิตร: 'l', liter: 'l', liters: 'l',
  ชิ้น: 'pcs', pc: 'pcs', piece: 'pcs', pieces: 'pcs', ขีด: 'heed',
};
const factors: Record<string, [string, number]> = {
  g: ['mass', 1], kg: ['mass', 1000], heed: ['mass', 100], ml: ['volume', 1], l: ['volume', 1000], pcs: ['count', 1],
};
export const stockUnits = [{ value: 'kg', label: 'กิโลกรัม (kg)' }, { value: 'g', label: 'กรัม (g)' },
  { value: 'l', label: 'ลิตร (l)' }, { value: 'ml', label: 'มิลลิลิตร (ml)' }, { value: 'pcs', label: 'ชิ้น' }];
export function normalizeRecipeUnit(unit: string): string {
  const value = unit.trim().toLowerCase();
  return aliases[value] ?? value;
}
export function recipeQuantity(value: number, from: string, to: string): number {
  const source = normalizeRecipeUnit(from), target = normalizeRecipeUnit(to);
  if (!source || !target) throw new Error('กรุณาระบุหน่วยวัตถุดิบและหน่วยสต็อก');
  if (source === target) return value;
  const a = factors[source], b = factors[target];
  if (!a || !b || a[0] !== b[0]) throw new Error(`หน่วย ${from} แปลงเป็น ${to} ไม่ได้ กรุณาเลือกหน่วยประเภทเดียวกัน`);
  return value * a[1] / b[1];
}
export function recipeError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message);
  if (Array.isArray(detail)) return 'กรุณาตรวจชื่อ หน่วย และต้นทุน (ต้องไม่ติดลบ)';
  return error instanceof Error ? error.message : 'เชื่อมต่อไม่สำเร็จ ข้อมูลที่กรอกยังอยู่ กรุณาลองใหม่';
}
