import { ArrowRight, BedDouble, Clock3, ShoppingCart, ShoppingBag, UtensilsCrossed, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { PLATFORM_BRAND } from "@/config/platformBrand";
import { registrationModules, type PlatformModuleKey } from "@/config/platformModules";

type ProductPresentation = {
  icon: LucideIcon;
  accent: string;
  surface: string;
  text: string;
};

const productPresentation: Partial<Record<PlatformModuleKey, ProductPresentation>> = {
  restaurant_pos: {
    icon: UtensilsCrossed,
    accent: "bg-orange-600",
    surface: "border-orange-200 bg-orange-50",
    text: "text-orange-700",
  },
  retail_pos: {
    icon: ShoppingCart,
    accent: "bg-emerald-600",
    surface: "border-emerald-200 bg-emerald-50",
    text: "text-emerald-700",
  },
  takeaway_pos: {
    icon: ShoppingBag,
    accent: "bg-slate-950",
    surface: "border-slate-300 bg-slate-100",
    text: "text-slate-800",
  },
  hotel_pms: {
    icon: BedDouble,
    accent: "bg-amber-600",
    surface: "border-amber-200 bg-amber-50",
    text: "text-amber-700",
  },
};

function presentationFor(key: PlatformModuleKey): ProductPresentation {
  return productPresentation[key] ?? {
    icon: ShoppingCart,
    accent: "bg-blue-600",
    surface: "border-blue-200 bg-blue-50",
    text: "text-blue-700",
  };
}

export default function SignupProductSelectorPage(): JSX.Element {
  const products = registrationModules();

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(249,115,22,0.16),_transparent_26%),radial-gradient(circle_at_bottom_right,_rgba(124,58,237,0.14),_transparent_30%),linear-gradient(180deg,_#f8fafc_0%,_#ffffff_100%)] px-4 py-12 text-slate-950">
      <div className="mx-auto max-w-6xl">
        <header className="mx-auto max-w-3xl text-center">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-blue-600">
            {PLATFORM_BRAND.customerRegisterName}
          </p>
          <h1 className="mt-3 text-3xl font-black tracking-tight sm:text-5xl">เลือกประเภทระบบสำหรับธุรกิจของคุณ</h1>
          <p className="mt-4 text-base leading-7 text-slate-600">
            Restaurant POS เปิดให้ทดลองใช้แล้ว ส่วน Retail POS, Takeaway POS และ Hotel PMS
            จะแจ้งเปิดรับสมัครเมื่อแต่ละระบบผ่านการทดสอบ
          </p>
        </header>

        <section className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-4" aria-label="ประเภทระบบที่เปิดให้สมัคร">
          {products.map((product) => {
            const presentation = presentationFor(product.key);
            const ProductIcon = presentation.icon;
            const isAvailable = product.registration === "open" && Boolean(product.registrationRoute);
            const content = (
              <>
                <div>
                  <div className={`flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-sm ${presentation.accent}`}>
                    <ProductIcon className="h-7 w-7" />
                  </div>
                  <p className={`mt-6 text-xs font-bold uppercase tracking-[0.16em] ${presentation.text}`}>
                    {isAvailable ? "เปิดรับสมัคร" : product.availability === "dark_launch" ? "ทดสอบภายใน" : "ยังไม่เปิดรับสมัคร"}
                  </p>
                  <h2 className="mt-2 text-2xl font-black">{product.title}</h2>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{product.description}</p>
                </div>
                <div className={`mt-10 flex items-center justify-between text-sm font-bold ${presentation.text}`}>
                  <span>{isAvailable ? "สมัครและเริ่มทดลองใช้" : "รอประกาศเปิดใช้งาน"}</span>
                  {isAvailable ? <ArrowRight className="h-4 w-4" /> : <Clock3 className="h-4 w-4" />}
                </div>
              </>
            );
            const className = `flex min-h-80 flex-col justify-between rounded-3xl border p-6 shadow-sm ${presentation.surface}`;
            if (isAvailable && product.registrationRoute) {
              return (
                <Link
                  key={product.key}
                  data-testid={`signup-product-${product.key}`}
                  to={product.registrationRoute}
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
