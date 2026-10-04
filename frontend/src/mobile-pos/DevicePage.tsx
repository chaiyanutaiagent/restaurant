import { Capacitor } from "@capacitor/core";
import { useState } from "react";
import { pairedTakeawayPrinters, savedTakeawayPrinter, saveTakeawayPrinter, printConfiguredLongReceiptTest,
  isNativeTakeawayPrinterAvailable, type TakeawayPrinterDevice } from "../lib/takeawayPrinter";

export default function DevicePage(): JSX.Element {
  const platform = Capacitor.getPlatform();
  const [devices, setDevices] = useState<TakeawayPrinterDevice[]>([]);
  const [selected, setSelected] = useState(savedTakeawayPrinter);
  const [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  async function scan() {
    setBusy(true); setMessage("");
    try { const list = await pairedTakeawayPrinters(); setDevices(list); if (!list.length) setMessage("ไม่พบอุปกรณ์ กรุณาจับคู่เครื่องพิมพ์ใน Bluetooth ของ Android ก่อน"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "อ่านเครื่องพิมพ์ไม่ได้"); }
    finally { setBusy(false); }
  }
  async function print() {
    setBusy(true); setMessage("");
    try { if (!await printConfiguredLongReceiptTest()) throw new Error("กรุณาเลือกเครื่องพิมพ์ก่อน"); setMessage("ส่งข้อมูลพิมพ์แล้ว กรุณาตรวจบิลจริง ภาษาไทย ความยาว และการตัดกระดาษ"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "ส่งข้อมูลพิมพ์ไม่ได้"); }
    finally { setBusy(false); }
  }
  return <section className="mx-auto max-w-2xl space-y-4 rounded-2xl border bg-white p-6">
    <h1 className="text-2xl font-bold">อุปกรณ์ Foodchainservice POS</h1>
    <p>แพลตฟอร์ม: {platform} · รุ่นทดลอง UAT</p>
    <h2 className="font-bold">กล้องสแกน QR</h2>
    <p>แอปจะขอสิทธิ์กล้องเมื่อกดสแกน หากไม่อนุญาต สามารถกรอกรหัสหรือบาร์โค้ดได้</p>
    <h2 className="font-bold">เครื่องพิมพ์และลิ้นชักเงิน</h2>
    {isNativeTakeawayPrinterAvailable() ? <div className="space-y-3">
      <p>Android Bluetooth ESC/POS · ใช้เครื่องพิมพ์ที่จับคู่ไว้แล้ว การส่งข้อมูลสำเร็จไม่ใช่การยืนยันว่าพิมพ์ออกครบ</p>
      <button disabled={busy} onClick={() => { void scan(); }} className="rounded-xl bg-emerald-700 p-3 text-white">ค้นหาเครื่องพิมพ์ที่จับคู่</button>
      {devices.map((device) => <button key={device.address} className="block w-full rounded-xl border p-3 text-left" onClick={() => { saveTakeawayPrinter(device); setSelected(device); }}>{device.name} · {device.address}</button>)}
      {selected && <><p>เครื่องที่เลือก: {selected.name}</p><button disabled={busy} onClick={() => { void print(); }} className="rounded-xl border p-3">พิมพ์บิลทดสอบ</button></>}
    </div> : <p>อุปกรณ์นี้ไม่มีไดรเวอร์ Android Bluetooth ของแอป ไม่รองรับการพิมพ์โดยตรงในโหมดนี้</p>}
    {message && <p role="status" className="rounded-xl bg-slate-100 p-3">{message}</p>}
    <p>ลิ้นชักเงินต้องต่อกับเครื่องพิมพ์ที่รองรับและตรวจรับการเปิดจริงก่อนใช้รับเงิน</p>
    <h2 className="font-bold">การอัปเดต</h2>
    <p>รุ่นนี้ไม่ใช้ช่องดาวน์โหลด APK ของ Takeaway เดิม และไม่ย้ายข้อมูลค้างส่งจากแอปเดิมโดยอัตโนมัติ</p>
    <p>{platform === "ios" ? "รอเตรียมบัญชี Apple และ TestFlight สำหรับแจกทดสอบ" : "รับรุ่นทดสอบจากผู้ดูแลระบบหลังตรวจรับ ห้ามถอนแอปเมื่อมีรายการค้างส่ง"}</p>
  </section>;
}
