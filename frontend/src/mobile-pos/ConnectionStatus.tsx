import { useEffect, useState } from "react";

export default function ConnectionStatus(): JSX.Element {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update); window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);
  return <div role="status" className={`px-4 py-2 text-center text-sm ${online ? "bg-slate-100 text-slate-600" : "bg-amber-100 font-bold text-amber-950"}`}>
    {online ? "POS UAT · เครื่องมีการเชื่อมต่อเครือข่าย — ไม่ใช่การยืนยันสถานะเซิร์ฟเวอร์" : "ออฟไลน์ · ยังเข้าสู่ระบบหรือยืนยันการส่งข้อมูลไม่ได้ อย่าล้างข้อมูลหรือติดตั้งแอปใหม่"}
  </div>;
}
