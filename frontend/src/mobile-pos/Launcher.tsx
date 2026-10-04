import { Link } from "react-router-dom";
import { ShoppingBag, Store, UtensilsCrossed } from "lucide-react";
import { POS_PRODUCTS } from "./products";

const icons = { takeaway: ShoppingBag, restaurant: UtensilsCrossed, retail: Store };

export default function Launcher(): JSX.Element {
  return <main className="mx-auto flex min-h-[80dvh] max-w-6xl flex-col justify-center gap-8 p-5 md:p-10">
    <header><p className="text-sm font-bold tracking-widest text-emerald-700">FOODCHAINSERVICE · UAT</p>
      <h1 className="mt-3 text-3xl font-black text-slate-950 md:text-4xl">เลือกระบบหน้าร้าน</h1>
      <p className="mt-3 max-w-2xl text-slate-600">แอปทดลองสำหรับพนักงาน ร้านและสาขาที่เข้าใช้ได้จะตรวจจากบัญชีของคุณ</p>
    </header>
    <div className="grid gap-4 md:grid-cols-3">{POS_PRODUCTS.map((product) => {
      const Icon = icons[product.id];
      return <section key={product.id} className="flex flex-col rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <Icon aria-hidden="true" className="mb-5 h-9 w-9 text-emerald-700" />
        <h2 className="text-2xl font-bold">{product.name}</h2>
        <p className="mb-6 mt-3 flex-1 text-slate-600">{product.description}</p>
        {product.available && product.path ? <Link className="rounded-xl bg-emerald-700 px-4 py-4 text-center font-bold text-white focus-visible:outline focus-visible:outline-4" to={product.path}>เข้าใช้ {product.name}</Link>
          : <button disabled className="rounded-xl bg-slate-100 px-4 py-4 font-semibold text-slate-500">{product.name} · รอเชื่อมระบบ</button>}
      </section>;
    })}</div>
    <aside className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
      <strong>รุ่นทดสอบ UAT</strong><p className="mt-1">รายการที่ส่งสำเร็จจะบันทึกในระบบทดสอบจริง ต้องอัปเดตเซิร์ฟเวอร์รองรับแอปรุ่นนี้ก่อนเข้าใช้ ส่วนเครื่องพิมพ์ เงินสด และการทำงานออฟไลน์บนเครื่องจริงยังต้องตรวจรับ</p>
    </aside>
  </main>;
}
