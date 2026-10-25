import { useEffect, useState } from "react";
import { deviceApi } from "@/lib/deviceApi";
import { useDeviceStore } from "@/stores/device.store";
import { useAuthStore, flushNativeSession } from "./session";
import { pairedTakeawayPrinters, savedTakeawayPrinter, saveTakeawayPrinter, printConfiguredLongReceiptTest, printConfiguredCutterTest, type TakeawayPrinterDevice } from "@/lib/takeawayPrinter";
import type { ApiResponse } from "@/types/api";
import type { DevicePairResponse } from "@/types/device";
import { nativeProduct, nativeBusinessType } from "./config";
import { recoverNativeRestaurantOrder, hasNativePaymentPending } from "./paidOrderRecovery";
import api, { authApi } from '@/lib/api';
import type { UserBranch } from '@/types/user';
import { acknowledgeNativeTransaction, readNativeTransaction, recoverNativeTransaction } from './transactionJournal';
import { nativeScope } from './storage';
import PairingScanner from './PairingScanner';
import { usePendingPairing } from './pairing';
import { checkPosUpdate, usePosUpdate } from './appUpdate';

export default function Device() {
  const checkingUpdate = usePosUpdate(state => state.checking);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [printers, setPrinters] = useState<TakeawayPrinterDevice[]>([]);
  const [printer, setPrinter] = useState(savedTakeawayPrinter());
  const device = useDeviceStore(state => state.device);
  const session = useAuthStore();
  const pending = usePendingPairing(state => state.pending);
  const [code, setCode] = useState("");
  const [pin, setPin] = useState("");
  useEffect(() => { setCode(pending?.deviceCode ?? ""); setPin(pending?.pin ?? ""); }, [pending]);
  const [branches, setBranches] = useState<UserBranch[]>([]);
  const [transaction, setTransaction] = useState<Awaited<ReturnType<typeof readNativeTransaction>>>(null);
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const refresh = () => { setOnline(navigator.onLine); void readNativeTransaction().then(setTransaction).catch(() => setError('อ่านประวัติธุรกรรมไม่ได้')); };
    refresh(); ['online', 'offline', 'native-pos-transaction'].forEach(event => window.addEventListener(event, refresh));
    return () => { ['online', 'offline', 'native-pos-transaction'].forEach(event => window.removeEventListener(event, refresh)); };
  }, []);
  return <main className="mx-auto max-w-xl space-y-5 p-5">
    <h1 className="text-2xl font-bold">ตั้งค่าเครื่องขาย</h1>
    <button disabled={busy || checkingUpdate} className="min-h-12 rounded border p-3" onClick={()=>{void checkPosUpdate(true);}}>{checkingUpdate?'กำลังตรวจเวอร์ชัน…':'ตรวจอัปเดตแอป'}</button>
    <p role="status">{online ? 'ออนไลน์' : 'ออฟไลน์ — หยุดบันทึก / รับเงิน'} · UAT {nativeProduct === 'retail' ? '0.1.0-uat.14' : '0.1.0-uat.6'}</p>
    <p className="break-all text-sm">บริษัท {session.businessSlug} · สาขา {session.branchId}</p>
    <button disabled={busy || !online} className="min-h-12 rounded border p-3" onClick={async () => {
      try { setBranches((await authApi.myBranches()).data.data.filter(item => item.business_type === nativeBusinessType && item.target_database === nativeBusinessType)); }
      catch { setError('โหลดสาขาที่มีสิทธิ์ไม่ได้'); }
    }}>เลือกสาขาอื่น</button>
    {branches.filter(item => item.branch_id !== session.branchId).map(item => <button key={item.branch_id} disabled={busy} className="block min-h-12 rounded border p-3" onClick={async () => {
      if (!confirm('เปลี่ยนสาขา? ตะกร้าจะเก็บแยกไว้สาขาเดิม และต้องจับคู่ Counter ของสาขาใหม่')) return;
      setBusy(true); try {
        if (await hasNativePaymentPending() || await readNativeTransaction()) throw new Error('ตรวจธุรกรรมค้างก่อนเปลี่ยนสาขา');
        const result = (await authApi.switchBranch(item.branch_id, item.station_key)).data.data;
        session.setSession(result, session.companyId!); await flushNativeSession();
        await useDeviceStore.getState().clearSession(); setBranches([]); setError('เปลี่ยนสาขาแล้ว กรุณาจับคู่เครื่องของสาขานี้');
      } catch (failure) { setError(failure instanceof Error ? failure.message : 'เปลี่ยนสาขาไม่ได้'); } finally { setBusy(false); }
    }}>{item.branch_name}</button>)}
    {transaction && <section className="space-y-3 rounded border border-amber-500 p-4">
      <h2 className="font-bold">ธุรกรรมรอตรวจสอบ — ห้ามรับเงินซ้ำ</h2>
      {transaction.scope === nativeScope() ? <p className="break-all">{transaction.url} · {transaction.at}</p> : <p>กรุณาออกจากระบบ แล้วเข้าสู่ระบบด้วยพนักงานและสาขาที่ทำรายการเดิม ข้อมูลรายการจะยังคงเก็บไว้</p>}
      <button disabled={busy || !online} className="min-h-12 rounded border p-3" onClick={async () => {
        setBusy(true); try { setTransaction(await recoverNativeTransaction(api)); setError('ตรวจผลกับ Server แล้ว กรุณาตรวจเลขเอกสารและยอดก่อนยืนยัน'); }
        catch (failure) { setError(failure instanceof Error ? failure.message : 'ยังตรวจสอบไม่ได้'); } finally { setBusy(false); }
      }}>ตรวจผล / ส่งคำขอเดิม</button>
      {transaction.scope === nativeScope() && transaction.result && <><p>เอกสาร {transaction.result.order_number ?? transaction.result.id ?? '—'} · สถานะ {transaction.result.status ?? 'Server ตอบสำเร็จ'} · ยอด {transaction.result.total_amount ?? '—'}</p>
        <button disabled={busy || transaction.result.status === 'pending_payment'} className="min-h-12 rounded border p-3" onClick={async () => {
          if (!confirm('ตรวจเอกสารกับ Server แล้ว และจะไม่รับเงินรายการนี้ซ้ำ ใช่หรือไม่?')) return;
          try { await acknowledgeNativeTransaction(); setTransaction(null); } catch (failure) { setError(String(failure)); }
        }}>รับทราบผลที่ยืนยันแล้ว</button></>}
      <p className="text-sm">กรณีปิดโต๊ะ ระบบตรวจสถานะเท่านั้น ไม่ส่งรับเงินซ้ำ หากยังไม่ยืนยัน ให้ผู้จัดการตรวจ Server โดยเก็บข้อมูลแอปไว้</p>
    </section>}
    {nativeProduct === 'restaurant' && <button disabled={busy} className="min-h-12 rounded border p-3" onClick={async () => {setBusy(true);try {const result=await recoverNativeRestaurantOrder();setError(`Server ยืนยันรายการเดิมแล้ว คิว ${result.order.queue_display ?? '—'} กรุณาตรวจบิลเดิมก่อนขายต่อ`);}catch(failure){setError(failure instanceof Error ? failure.message : 'ยังยืนยันรายการไม่ได้');}finally{setBusy(false);}}}>ตรวจ / กู้คืนรายการรับเงินเดิม</button>}
    <p>เครื่องปัจจุบัน: {device?.device_code ?? 'ยังไม่จับคู่'}</p>
    <PairingScanner disabled={busy} />
    <p className="text-sm">ใช้รหัสและ PIN ของเครื่อง Counter ในสาขาที่เลือก จากผู้จัดการร้าน</p>
    <form className="space-y-4" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError('');
      const data = new FormData(e.currentTarget);
      try {
        if (!navigator.onLine) throw new Error('กรุณาเชื่อมต่ออินเทอร์เน็ต');
        if (pending && (pending.companyId !== session.companyId || (pending.branchId && pending.branchId !== session.branchId))) throw new Error('QR ไม่ตรงกับบริษัทหรือสาขาที่เข้าสู่ระบบ');
        if (pending?.expiresAt && pending.expiresAt <= Date.now()) throw new Error('QR หมดอายุแล้ว กรุณาขอ PIN ใหม่');
        if (await hasNativePaymentPending() || await readNativeTransaction()) throw new Error('ตรวจธุรกรรมค้างก่อนเปลี่ยนเครื่องขาย');
        if (device && !confirm('เครื่องนี้จับคู่อยู่แล้ว ต้องการเปลี่ยน Counter ใช่หรือไม่?')) return;
        const result = (await deviceApi.post<ApiResponse<DevicePairResponse>>('/device-auth/pair', { company_id: session.companyId, device_code: String(data.get('code')).trim().toUpperCase(), pairing_pin: String(data.get('pin')) })).data.data;
        if (result.device.company_id !== session.companyId || result.device.branch_id !== session.branchId || result.device.brand_id !== session.brandId || result.device.business_type !== nativeBusinessType || result.device.target_database !== nativeBusinessType || result.device.device_type !== 'counter') throw new Error('เครื่องนี้ไม่ใช่ Counter ของสาขาและระบบที่เลือก');
        await useDeviceStore.getState().setSession(result);
        usePendingPairing.getState().clear(); setCode(''); setPin('');
        setError('จับคู่สำเร็จแล้ว กลับหน้าขายเพื่อเปิดกะได้');
      } catch (failure) { setError(failure instanceof Error ? failure.message : 'จับคู่ไม่ได้'); }
      finally { setBusy(false); }
    }}>
      <label className="block">รหัสเครื่อง<input name="code" value={code} readOnly={Boolean(pending)} onChange={event => setCode(event.target.value)} required disabled={busy} className="block min-h-12 w-full rounded border p-3"/></label>
      <label className="block">PIN จับคู่<input name="pin" value={pin} readOnly={Boolean(pending)} onChange={event => setPin(event.target.value)} required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} disabled={busy} className="block min-h-12 w-full rounded border p-3"/></label>
      {pending && <button type="button" disabled={busy} className="min-h-12 rounded border p-3" onClick={() => usePendingPairing.getState().clear()}>ล้าง QR เพื่อกรอกรหัสเอง</button>}
      <button disabled={busy} className="min-h-12 rounded bg-blue-700 p-3 text-white">จับคู่เครื่อง</button>
    </form>
    <h2 className="text-xl font-bold">เครื่องพิมพ์ Bluetooth</h2>
    <p>{printer?.name ?? 'ยังไม่เลือกเครื่องพิมพ์'}</p>
    <button className="min-h-12 rounded border p-3" onClick={async () => {try {setError('');setPrinters(await pairedTakeawayPrinters());}catch {setError('ตรวจการอนุญาต Bluetooth และจับคู่เครื่องพิมพ์ใน Android ก่อน');}}}>ค้นหาเครื่องพิมพ์ที่จับคู่แล้ว</button>
    {printers.map(item => <button key={item.address} className="block min-h-12 w-full rounded border p-3" onClick={() => {saveTakeawayPrinter(item);setPrinter(item);}}>{item.name} · {item.address}</button>)}
    <button disabled={busy || !printer} className="min-h-12 rounded border p-3" onClick={async () => {
      setBusy(true); try { if (!await printConfiguredLongReceiptTest()) throw new Error('ยังไม่มีเครื่องพิมพ์'); setError('ส่งใบพิมพ์ทดสอบแล้ว กรุณาตรวจภาษาไทยและความกว้างกระดาษ'); }
      catch (failure) { setError(failure instanceof Error ? failure.message : 'พิมพ์ไม่ได้ ตรวจ Bluetooth และกระดาษ'); } finally { setBusy(false); }
    }}>พิมพ์ทดสอบภาษาไทย</button>
    <button disabled={busy || !printer || !online} className="min-h-12 rounded border p-3" onClick={async () => {
      setBusy(true); setError('');
      try {
        if (!await printConfiguredCutterTest()) throw new Error('ยังไม่ได้เลือกเครื่องพิมพ์');
        setError('ส่งคำสั่งเลื่อนและตัดกระดาษแล้ว กรุณาตรวจที่เครื่องจริง หากไม่ตัด ห้ามสรุปว่าเครื่องพร้อมใช้งาน');
      } catch (failure) { setError(failure instanceof Error ? failure.message : 'ส่งคำสั่งไม่ได้ อาจพิมพ์บางส่วนแล้ว กรุณาตรวจเครื่องก่อนลองอีกครั้ง'); }
      finally { setBusy(false); }
    }}>ทดสอบตัดกระดาษ</button>
    <p className="text-sm text-amber-800">ต้องทดสอบใบเสร็จภาษาไทย กระดาษหมด และเชื่อมต่อใหม่กับรุ่นเครื่องจริงก่อนเปิดใช้</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </main>;
}
