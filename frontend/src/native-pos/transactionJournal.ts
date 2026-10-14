import { SecureStorage } from '@aparajita/capacitor-secure-storage';
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { nativeProduct, assertNativeRequest } from './config';
import { nativeScope, clearNativeCart } from './storage';
import { useAuthStore } from '@/stores/auth.store';

const key = `foodchainservice.${nativeProduct}.uat.transaction.v1`;
type Journal = { scope: string; url: string; data: string; at: string; replayable: boolean; ambiguous: boolean; result?: Record<string, any> };
type Config = InternalAxiosRequestConfig & { nativeJournal?: boolean; nativeReplay?: boolean };
let lock: Promise<unknown> = Promise.resolve();
function serial<T>(action: () => Promise<T>): Promise<T> {
  const next = lock.then(action); lock = next.catch(() => undefined); return next;
}
export async function readNativeTransaction(): Promise<Journal | null> {
  const raw = await SecureStorage.getItem(key);
  return typeof raw === 'string' ? JSON.parse(raw) : null;
}
const save = (entry: Journal) => SecureStorage.setItem(key, JSON.stringify(entry));
const financial = (url: string) => /^\/pos\/(sales|refunds|shifts\/open|shifts\/[^/]+\/(close|handover|cash-movements)|refunds\/[^/]+\/(cash-confirm|retry))$/.test(url)
  || /^\/restaurant\/sessions\/[^/]+\/checkout$/.test(url);
const authentication = (url: string) => ['/auth/login', '/auth/refresh', '/auth/logout'].includes(url);

// A receipt response is not durable until stored. Unknown outcomes fail closed.
// Only endpoints with an existing server idempotency key may be replayed.
export function installNativeTransactionJournal(api: AxiosInstance) {
  const processedResponses = new WeakSet<object>();
  api.interceptors.request.use(config => serial(async () => {
    const url = config.url ?? '';
    assertNativeRequest(url, config.method ?? 'get', useAuthStore.getState(), navigator.onLine);
    if (['get', 'head', 'options'].includes((config.method ?? 'get').toLowerCase()) || authentication(url)) return config;
    const prior = await readNativeTransaction();
    const data = typeof config.data === 'string' ? config.data : JSON.stringify(config.data ?? {});
    if (prior) {
      // Allow completion of this exact provider payment, but never a new sale.
      const body = JSON.parse(data);
      if (prior.scope === nativeScope() && prior.result?.status === 'pending_payment'
          && ((url === '/payments/sessions/promptpay' && body.reference_id === prior.result.id)
            || /^\/payments\/sessions\/[^/]+\/check$/.test(url))) return config;
      const s = useAuthStore.getState();
      const [company, , branch, user] = prior.scope.split(':');
      if (url === '/auth/switch-branch' && s.companyId === company && s.user?.id === user && body.branch_id === branch) return config;
      if (!((config as Config).nativeJournal && prior.scope === nativeScope() && prior.url === url && prior.data === data && prior.replayable && !prior.result)) {
        throw new Error('มีธุรกรรมเดิมรอตรวจสอบ เปิด เครื่องขาย / พิมพ์ เพื่อยืนยันผลก่อนทำรายการใหม่');
      }
    }
    if (!financial(url)) return config;
    if (!navigator.onLine) throw new Error('ต้องออนไลน์ก่อนทำธุรกรรม');
    const body = JSON.parse(data);
    const entry = prior ?? { scope: nativeScope(), url, data, at: new Date().toISOString(), ambiguous: false,
      replayable: url.startsWith('/pos/') && Boolean(body.client_order_id || body.idempotency_key) };
    await save(entry);
    (config as Config).nativeJournal = true;
    return config;
  }));
  api.interceptors.response.use(async response => {
    // Axios auth refresh can feed the same response through this chain twice.
    if (processedResponses.has(response)) return response;
    if ((response.config as Config).nativeJournal) {
      const entry = await readNativeTransaction();
      if (!entry || entry.scope !== nativeScope()) throw new Error('บริบทธุรกรรมเปลี่ยน กรุณาตรวจรายการเดิม');
      entry.result = response.data.data;
      await save(entry);
      if (entry.url === '/pos/sales') {
        await clearNativeCart(`${entry.scope}:counter`);
        await clearNativeCart(`${entry.scope}:takeaway`);
      }
      await SecureStorage.setItem(`${key}.last`, JSON.stringify(entry));
      if (entry.url !== '/pos/sales' && !(response.config as Config).nativeReplay) await SecureStorage.removeItem(key);
      // Leave the durable result until the caller's UI has consumed it. On restart
      // the Device screen requires an explicit acknowledgement before new writes.
      window.dispatchEvent(new Event('native-pos-transaction'));
      processedResponses.add(response);
    }
    return response;
  }, async error => {
    if ((error.config as Config | undefined)?.nativeJournal) {
      const entry = await readNativeTransaction();
      if (entry && !entry.result) {
        if (!entry.ambiguous && [400, 403, 404, 422].includes(error.response?.status)) await SecureStorage.removeItem(key);
        else { entry.ambiguous = true; await save(entry); }
        window.dispatchEvent(new Event('native-pos-transaction'));
      }
    }
    throw error;
  });
}
export async function acknowledgeNativeTransaction() {
  const entry = await readNativeTransaction();
  if (!entry) return;
  if (entry.scope !== nativeScope() || !entry.result || entry.result.status === 'pending_payment') throw new Error('ยังยืนยันผลธุรกรรมไม่ได้ ห้ามล้างหรือสร้างรายการซ้ำ');
  await SecureStorage.removeItem(key);
  window.dispatchEvent(new Event('native-pos-transaction'));
}
export async function recoverNativeTransaction(api: AxiosInstance) {
  const entry = await readNativeTransaction();
  if (!entry) throw new Error('ไม่มีธุรกรรมรอตรวจสอบ');
  if (entry.scope !== nativeScope()) throw new Error('เข้าสู่ระบบด้วยพนักงานและสาขาเดิมก่อนตรวจรายการ');
  if (entry.result?.status === 'pending_payment') {
    entry.result = (await api.get(`/pos/sales/${entry.result.id}`)).data.data;
    await save(entry); return entry;
  }
  if (entry.result) return entry;
  if (!entry.replayable) {
    if (!/^\/restaurant\/sessions\/[^/]+\/checkout$/.test(entry.url)) throw new Error('คำขอนี้ไม่มีรหัสป้องกันการทำซ้ำ ให้ผู้จัดการตรวจ Server โดยห้ามส่งซ้ำหรือล้างข้อมูลแอป');
    const sessionUrl = entry.url.replace(/\/checkout$/, '/detail');
    const session = (await api.get(sessionUrl)).data.data;
    if (session.status !== 'closed' || !session.sale_order_id) throw new Error('ยังไม่พบการปิดโต๊ะที่ยืนยันแล้ว ให้ผู้จัดการตรวจ Server ห้ามส่งชำระซ้ำ');
    entry.result = (await api.get(`/pos/sales/${session.sale_order_id}`)).data.data;
    await save(entry); return entry;
  }
  await api.request({ method: 'post', url: entry.url, data: JSON.parse(entry.data), nativeJournal: true, nativeReplay: true } as Config);
  return (await readNativeTransaction())!;
}
