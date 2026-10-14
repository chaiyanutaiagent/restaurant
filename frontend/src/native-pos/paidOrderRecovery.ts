import { SecureStorage } from "@aparajita/capacitor-secure-storage";
import { useAuthStore } from "@/stores/auth.store";
import { wapApi, type WapMenu, type WapPaidOrderPayload } from "@/lib/wapApi";
import { nativeScope, clearNativeCart } from './storage';
import type { WapOrder } from '@/lib/wapApi';

const key = 'foodchainservice.restaurant.uat.online-payment.v1';
type Pending = { companyId: string; branchId: string; userId: string; brandSlug?: string; payload: WapPaidOrderPayload; comparison: string; result?: WapOrder };
let busy = false;
export async function hasNativePaymentPending() { return typeof await SecureStorage.getItem(key) === 'string'; }
// Persist the online request BEFORE sending; an interrupted response is not a successful payment.
// Retry only the exact same payload/client id, never silently convert to an offline sale.
export async function submitNativeRestaurantOrder(brandSlug: string | undefined, payload: WapPaidOrderPayload, _menu?: WapMenu) {
  if (busy) throw new Error('กำลังตรวจรายการเดิม กรุณารอสักครู่');
  if (!navigator.onLine) throw new Error('ต้องออนไลน์ก่อนตรวจยอดและรับชำระเงิน');
  busy = true;
  try {
    const state = useAuthStore.getState();
    if (!state.companyId || !state.branchId || !state.user) throw new Error('บริบทพนักงานไม่ครบ');
    const { client_order_id: ignored, ...base } = payload;
    const comparison = JSON.stringify({ ...base, is_offline: false });
    const raw = await SecureStorage.getItem(key);
    let pending: Pending;
    if (typeof raw === 'string') {
      pending = JSON.parse(raw);
      if (pending.companyId !== state.companyId || pending.branchId !== state.branchId || pending.userId !== state.user.id || pending.comparison !== comparison || pending.brandSlug !== brandSlug) {
        throw new Error('มีรายการชำระเงินเดิมรอตรวจสอบ เปิดหน้าตั้งค่าเครื่องขายเพื่อกู้คืนก่อนสร้างบิลใหม่');
      }
    } else {
      pending = { companyId: state.companyId, branchId: state.branchId, userId: state.user.id, brandSlug,
        comparison, payload: { ...payload, client_order_id: `native-${crypto.randomUUID()}`, is_offline: false } };
      await SecureStorage.setItem(key, JSON.stringify(pending));
      window.dispatchEvent(new Event('native-pos-transaction'));
    }
    const order = pending.result ?? (await wapApi.createPaidOrder(pending.payload, pending.brandSlug)).data.data;
    pending.result = order;
    await SecureStorage.setItem(key, JSON.stringify(pending));
    await clearNativeCart(`${nativeScope()}:takeaway`);
    await clearNativeCart(`${nativeScope()}:counter`);
    await SecureStorage.removeItem(key);
    window.dispatchEvent(new Event('native-pos-transaction'));
    return { order, status: 'reconciled' as const };
  } finally { busy = false; }
}
export async function recoverNativeRestaurantOrder() {
  const raw = await SecureStorage.getItem(key);
  if (typeof raw !== 'string') throw new Error('ไม่มีรายการรอตรวจสอบ');
  const pending: Pending = JSON.parse(raw);
  return submitNativeRestaurantOrder(pending.brandSlug, pending.payload);
}
export async function isPendingRestaurantBranchRestore(branchId: string) {
  const raw = await SecureStorage.getItem(key);
  if (typeof raw !== 'string') return false;
  const pending: Pending = JSON.parse(raw);
  const s = useAuthStore.getState();
  return s.companyId === pending.companyId && s.user?.id === pending.userId && branchId === pending.branchId;
}
