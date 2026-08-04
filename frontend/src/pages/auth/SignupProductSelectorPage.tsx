import { ArrowRight, Clock3, ShoppingCart, ShoppingBag, UtensilsCrossed } from "lucide-react";
import { Link } from "react-router-dom";

const products = [
  {
    key: "restaurant",
    title: "Restaurant & Cafe",
    eyebrow: "เปิดรับสมัคร",
    description: "ระบบร้านอาหารและคาเฟ่ จัดการสาขา โต๊ะ ออเดอร์ ครัว คิว เมนู และ QR",
    availability: "available" as const,
    to: "/signup/restaurant",
    icon: UtensilsCrossed,
    accent: "bg-orange-600",
    surface: "border-orange-200 bg-orange-50",
    text: "text-orange-700",
  },
  {
    key: "retail",
    title: "Retail POS",
    eyebrow: "แผนงาน Phase 7",
    description: "ระบบขายสินค้าทั่วไป สแกนสินค้า เปิดกะ รับชำระเงิน และจัดการสต็อกหน้าร้าน",
    availability: "planned" as const,
    icon: ShoppingCart,
    accent: "bg-emerald-600",
    surface: "border-emerald-200 bg-emerald-50",
    text: "text-emerald-700",
  },
  {
    key: "takeaway",
    title: "Takeaway Shop",
    eyebrow: "แผนงาน Phase 6",
    description: "ระบบขายอาหารแบบสั่งกลับบ้าน รับออเดอร์ จัดคิว ครัว และจุดรับอาหาร",
    availability: "planned" as const,
    icon: ShoppingBag,
    accent: "bg-violet-600",
    surface: "border-violet-200 bg-violet-50",
    text: "text-violet-700",
  },
];

export default function SignupProductSelectorPage(): JSX.Element {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(249,115,22,0.16),_transparent_26%),radial-gradient(circle_at_bottom_right,_rgba(124,58,237,0.14),_transparent_30%),linear-gradient(180deg,_#f8fafc_0%,_#ffffff_100%)] px-4 py-12 text-slate-950">
      <div className="mx-auto max-w-6xl">
        <header className="mx-auto max-w-3xl text-center">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-blue-600">เริ่มต้นใช้งาน SaaS</p>
          <h1 className="mt-3 text-3xl font-black tracking-tight sm:text-5xl">เลือกประเภทระบบสำหรับธุรกิจของคุณ</h1>
          <p className="mt-4 text-base leading-7 text-slate-600">
            Restaurant & Cafe เปิดให้ทดลองใช้แล้ว ส่วน Retail POS และ Takeaway Shop จะแจ้งเปิดรับสมัครตามแผนงานของแต่ละเฟส
          </p>
        </header>

        <section className="mt-10 grid gap-5 md:grid-cols-3" aria-label="ประเภทระบบที่เปิดให้สมัคร">
          {products.map((product) => {
            const content = (
              <>
                <div>
                  <div className={`flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-sm ${product.accent}`}>
                    <product.icon className="h-7 w-7" />
                  </div>
                  <p className={`mt-6 text-xs font-bold uppercase tracking-[0.16em] ${product.text}`}>{product.eyebrow}</p>
                  <h2 className="mt-2 text-2xl font-black">{product.title}</h2>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{product.description}</p>
                </div>
                <div className={`mt-10 flex items-center justify-between text-sm font-bold ${product.text}`}>
                  <span>{product.availability === "available" ? "สมัครและเริ่มทดลองใช้" : "ยังไม่เปิดรับสมัคร"}</span>
                  {product.availability === "available" ? <ArrowRight className="h-4 w-4" /> : <Clock3 className="h-4 w-4" />}
                </div>
              </>
            );
            const className = `flex min-h-80 flex-col justify-between rounded-3xl border p-6 shadow-sm ${product.surface}`;
            if (product.availability === "available") {
              return (
                <Link
                  key={product.key}
                  data-testid={`signup-product-${product.key}`}
                  to={product.to}
                  className={`${className} transition hover:-translate-y-1 hover:shadow-xl`}
                >
                  {content}
                </Link>
              );
            }
            return (
              <article
                key={product.key}
                data-testid={`signup-product-${product.key}`}
                aria-disabled="true"
                className={`${className} opacity-75`}
              >
                {content}
              </article>
            );
          })}
        </section>

        <footer className="mt-8 text-center text-sm text-slate-500">
          มีบัญชีแล้ว? <Link className="font-semibold text-blue-600 hover:text-blue-800" to="/login">เข้าสู่ระบบ</Link>
        </footer>
      </div>
    </main>
  );
}
