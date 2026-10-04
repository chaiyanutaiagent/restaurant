import { useEffect } from "react";
const dirty = new Set<string>();
const writes = new Set<string>();
export function beginNativeWrite(id: string): void { writes.add(id); }
export function endNativeWrite(id?: string): void { if (id) writes.delete(id); }
export function useNativePosWorkGuard(key: string, active: boolean): void {
  useEffect(() => {
    if (import.meta.env.VITE_APP_SURFACE !== "pos-uat") return;
    if (active) dirty.add(key); else dirty.delete(key);
    return () => { dirty.delete(key); };
  }, [key, active]);
}
export function assertNoNativeDraft(): void {
  if (writes.size) throw new Error("กำลังบันทึกหรือยืนยันรายการ กรุณารอให้เสร็จ");
  if (dirty.size) throw new Error("มีบิลที่กำลังทำ กรุณาบันทึก พักบิล หรือล้างตะกร้าก่อนเปลี่ยนหน้าหรือออกจากระบบ");
}
