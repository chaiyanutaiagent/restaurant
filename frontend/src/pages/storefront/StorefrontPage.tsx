import { useQuery } from "@tanstack/react-query";
import { Clock3, MapPin, Navigation, Phone, Search, ShieldCheck, ShoppingBag, Store, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { storefrontApi } from "@/lib/storefrontApi";
import { formatThaiCurrency } from "@/lib/cartUtils";
import { useOnlineStatus } from "@/lib/syncService";
import { SystemState } from "@/components/ui/system-state";
import type { StorefrontBranch, StorefrontProduct, StorefrontSummary } from "@/types/storefront";

function todayWorkingHours(branch: StorefrontBranch): string {
  if (!branch.working_hours) return "ดูเวลาทำการที่ร้าน";
  const keys = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
  const todayKey = keys[new Date().getDay()];
  const row = branch.working_hours[todayKey];
  if (!row) return "ดูเวลาทำการที่ร้าน";
  if (row.closed) return "วันนี้ปิด";
  if (row.open && row.close) return `วันนี้ ${row.open} - ${row.close}`;
  return "ดูเวลาทำการที่ร้าน";
}

export default function StorefrontPage(): JSX.Element {
  const { businessSlug } = useParams();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedBranchId, setSelectedBranchId] = useState<string>("");
  const isOnline = useOnlineStatus();

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(search), 250);
    return () => window.clearTimeout(timeout);
  }, [search]);

  const summaryQuery = useQuery({
    queryKey: ["storefront", businessSlug ?? "legacy", "summary"],
    queryFn: async () => (await storefrontApi.summary(businessSlug)).data.data as StorefrontSummary,
  });

  const productsQuery = useQuery({
    queryKey: ["storefront", businessSlug ?? "legacy", "products", debouncedSearch, selectedCategory],
    queryFn: async () =>
      (await storefrontApi.products({
        search: debouncedSearch || undefined,
        category_id: selectedCategory || undefined,
        in_stock_only: false,
        page: 1,
        limit: 24,
      }, businessSlug)).data,
  });

  const company = summaryQuery.data?.company ?? null;
  const branches = summaryQuery.data?.branches ?? [];
  const featuredProducts = summaryQuery.data?.featured_products ?? [];
  const experience = summaryQuery.data?.experience ?? null;
  const products = productsQuery.data?.data ?? [];
  const selectedBranch = useMemo(
    () => branches.find((branch) => branch.id === selectedBranchId) ?? branches[0] ?? null,
    [branches, selectedBranchId],
  );
  const categoryOptions = useMemo(() => {
    const map = new Map<string, string>();
    [...featuredProducts, ...products].forEach((product) => {
      if (product.category_id && product.category_name) {
        map.set(product.category_id, product.category_name);
      }
    });
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [featuredProducts, products]);

  useEffect(() => {
    if (!selectedBranchId && branches[0]) {
      setSelectedBranchId(branches[0].id);
    }
  }, [branches, selectedBranchId]);

  const isStale = Boolean(
    experience
    && Date.now() - new Date(experience.generated_at).getTime() > experience.stale_after_seconds * 1000,
  );

  if (summaryQuery.isPending && !summaryQuery.data) {
    return <PublicPageState kind={isOnline ? "loading" : "offline"} onRetry={() => void summaryQuery.refetch()} />;
  }

  if (summaryQuery.isError && !summaryQuery.data) {
    return <PublicPageState kind={isOnline ? "error" : "offline"} onRetry={() => void summaryQuery.refetch()} />;
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(249,115,22,0.20),_transparent_24%),radial-gradient(circle_at_bottom_right,_rgba(37,99,235,0.18),_transparent_28%),linear-gradient(180deg,_#fff7ed_0%,_#f8fafc_45%,_#eef2ff_100%)] text-slate-900">
      <section className="mx-auto max-w-7xl px-6 py-8 md:px-10">
        <div className="rounded-[36px] border border-white/80 bg-white/80 p-6 shadow-[0_28px_100px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="inline-flex items-center rounded-full bg-amber-100 px-4 py-1 text-xs font-semibold tracking-[0.18em] text-amber-800">
                แคตตาล็อกสินค้าและข้อมูลสาขา
              </div>
              <h1 className="mt-4 text-4xl font-semibold tracking-tight text-slate-950 md:text-6xl">
                {company?.name ?? "Foodchainservice Store"}
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600 md:text-lg">
                ชมสินค้า ตรวจสอบสถานะเบื้องต้น และค้นหาสาขาได้จากหน้าสาธารณะเดียวกัน
              </p>
              <div data-testid="catalog-only-notice" className="mt-5 flex max-w-2xl gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm leading-6 text-blue-900">
                <ShieldCheck className="mt-0.5 h-5 w-5 flex-none" aria-hidden="true" />
                <div><strong>หน้านี้เป็นแคตตาล็อกเท่านั้น</strong><br />ยังไม่เปิดตะกร้า สั่งซื้อ ชำระเงิน หรือบัญชีสมาชิก หากต้องการซื้อสินค้า กรุณาติดต่อสาขาโดยตรง</div>
              </div>
              <div className="mt-5 flex flex-wrap gap-3 text-sm text-slate-600">
                {company?.phone ? <span className="rounded-full bg-slate-100 px-4 py-2">{company.phone}</span> : null}
                {company?.address ? <span className="rounded-full bg-slate-100 px-4 py-2">{company.address}</span> : null}
                <Link className="rounded-full bg-slate-900 px-4 py-2 text-white" to={businessSlug ? `/${businessSlug}/admin` : "/login"}>สำหรับพนักงาน</Link>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <MetricCard label="สินค้าที่แสดง" value={String(products.length || featuredProducts.length)} />
              <MetricCard label="สาขาพร้อมขาย" value={String(branches.filter((branch) => branch.is_pickup_available).length)} />
              <MetricCard label="สินค้าแนะนำ" value={String(featuredProducts.length)} />
            </div>
          </div>
        </div>
      </section>

      {!isOnline || isStale ? (
        <section className="mx-auto max-w-7xl px-6 pb-6 md:px-10">
          <div className={`flex items-start gap-3 rounded-2xl border p-4 text-sm ${!isOnline ? "border-amber-200 bg-amber-50 text-amber-900" : "border-orange-200 bg-orange-50 text-orange-900"}`} role="status">
            {!isOnline ? <WifiOff className="mt-0.5 h-5 w-5 flex-none" /> : <Clock3 className="mt-0.5 h-5 w-5 flex-none" />}
            <div>
              <strong>{!isOnline ? "อุปกรณ์ออฟไลน์" : "ข้อมูลอาจล่าช้า"}</strong>
              <p className="mt-1">{!isOnline ? "กำลังแสดงข้อมูลที่โหลดไว้ การค้นหาหรือสถานะสินค้าอาจไม่เป็นปัจจุบัน" : "กรุณาโหลดใหม่ก่อนใช้ข้อมูลสินค้าและสาขาในการตัดสินใจ"}</p>
            </div>
          </div>
        </section>
      ) : null}

      <section className="mx-auto grid max-w-7xl gap-8 px-6 pb-16 md:px-10 xl:grid-cols-[1.35fr_0.9fr]">
        <div className="space-y-8">
          <div className="rounded-[32px] border border-white/80 bg-white/82 p-6 shadow-[0_20px_80px_rgba(15,23,42,0.08)] backdrop-blur">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.28em] text-blue-600">Product Catalog</p>
                <h2 className="mt-2 text-2xl font-semibold text-slate-950">รายการสินค้า</h2>
              </div>
              <div className="relative md:w-[24rem]">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
                <input
                  className="h-11 w-full rounded-xl border border-slate-200 bg-white pl-10 pr-4 text-sm"
                  placeholder="ค้นหาชื่อสินค้า"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
            </div>
            <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
              <button
                type="button"
                className={`rounded-full px-4 py-2 text-sm ${selectedCategory === "" ? "bg-blue-600 text-white" : "border border-slate-200 bg-slate-50 text-slate-700"}`}
                onClick={() => setSelectedCategory("")}
              >
                ทั้งหมด
              </button>
              {categoryOptions.map((category) => (
                <button
                  key={category.id}
                  type="button"
                  className={`rounded-full px-4 py-2 text-sm ${selectedCategory === category.id ? "bg-blue-600 text-white" : "border border-slate-200 bg-slate-50 text-slate-700"}`}
                  onClick={() => setSelectedCategory(category.id)}
                >
                  {category.name}
                </button>
              ))}
            </div>

            {productsQuery.isError ? (
              <div className="mt-6"><SystemState compact kind={isOnline ? "error" : "offline"} onAction={() => void productsQuery.refetch()} /></div>
            ) : null}
            {!productsQuery.isError && productsQuery.isFetching && products.length === 0 ? (
              <div className="mt-6"><SystemState compact kind="loading" /></div>
            ) : null}
            {!productsQuery.isError && !productsQuery.isFetching && (products.length > 0 ? products : featuredProducts).length === 0 ? (
              <div className="mt-6"><SystemState compact kind={debouncedSearch || selectedCategory ? "no_results" : "empty"} /></div>
            ) : null}
            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {(products.length > 0 ? products : featuredProducts).map((product) => (
                <article key={product.id} className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex h-48 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,_#e0f2fe,_#fff7ed)]">
                    {product.image_url ? (
                      <img src={product.image_url} alt={product.name} className="h-full w-full rounded-2xl object-cover" />
                    ) : (
                      <ShoppingBag className="h-10 w-10 text-slate-400" />
                    )}
                  </div>
                  <div className="mt-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-semibold text-slate-900">{product.name}</h3>
                        <p className="mt-1 text-xs text-slate-500">{product.category_name || "สินค้า"}</p>
                      </div>
                      <span className={`rounded-full px-3 py-1 text-xs font-medium ${product.in_stock ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                        {product.in_stock ? "พร้อมขาย" : "สินค้าหมด"}
                      </span>
                    </div>
                    <p className="mt-3 line-clamp-2 min-h-[2.75rem] text-sm text-slate-600">{product.description || "รายละเอียดสินค้าจะถูกแสดงที่นี่"}</p>
                    <div className="mt-4 flex items-end justify-between">
                      <div>
                        <div className="text-xs uppercase tracking-[0.2em] text-slate-500">ราคา</div>
                        <div className="mt-1 text-xl font-semibold text-blue-700">{formatThaiCurrency(Number(product.selling_price))}</div>
                      </div>
                      <div className="text-right text-xs text-slate-500">
                        <div>{product.vat_type === "included" ? `รวม VAT ${product.vat_rate}%` : product.vat_type === "excluded" ? `VAT ${product.vat_rate}% แยกนอก` : "ยกเว้น VAT"}</div>
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>

        <aside className="space-y-8">
          <div data-testid="public-capability-status" className="rounded-[32px] border border-blue-200 bg-blue-50/90 p-6 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold text-blue-800"><ShieldCheck className="h-5 w-5" />สถานะบริการสาธารณะ</div>
            <h2 className="mt-2 text-xl font-semibold text-slate-950">เปิดดูสินค้าและค้นหาสาขา</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">ข้อมูลและความสามารถทั้งหมดมาจากเซิร์ฟเวอร์ หน้านี้จะไม่แสดงผลสำเร็จของคำสั่งซื้อหรือการชำระเงินที่ยังไม่เปิดใช้</p>
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <Capability active={Boolean(experience?.capabilities.catalog)} label="แคตตาล็อก" />
              <Capability active={Boolean(experience?.capabilities.branch_locator)} label="ค้นหาสาขา" />
              <Capability active={Boolean(experience?.capabilities.checkout)} label="สั่งซื้อ" />
              <Capability active={Boolean(experience?.capabilities.payment)} label="ชำระเงิน" />
            </div>
          </div>
          <div className="rounded-[32px] border border-white/80 bg-white/82 p-6 shadow-[0_20px_80px_rgba(15,23,42,0.08)] backdrop-blur">
            <p className="text-sm font-semibold uppercase tracking-[0.28em] text-emerald-600">Store Locator</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950">ค้นหาสาขาและวางแผนไปรับสินค้า</h2>
            <div className="mt-5 grid gap-3">
              {branches.length === 0 ? <SystemState compact kind="empty" title="ยังไม่มีสาขาที่เปิดเผย" description="กรุณาติดต่อร้านโดยตรงหากต้องการข้อมูลเพิ่มเติม" /> : null}
              {branches.map((branch) => (
                <button
                  key={branch.id}
                  type="button"
                  onClick={() => setSelectedBranchId(branch.id)}
                  className={`rounded-2xl border p-4 text-left transition ${selectedBranch?.id === branch.id ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-white"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-slate-900">{branch.name}</div>
                      <div className="mt-1 text-sm text-slate-500">{branch.landmark || branch.address || "ดูรายละเอียดสาขา"}</div>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs font-medium ${branch.is_pickup_available ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                      {branch.is_pickup_available ? "พร้อมรับที่ร้าน" : "สาขานี้ยังไม่เปิดรับ"}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {selectedBranch ? (
            <div className="rounded-[32px] border border-slate-200 bg-[linear-gradient(180deg,_#0f172a_0%,_#1e293b_100%)] p-6 text-white shadow-[0_20px_80px_rgba(15,23,42,0.22)]">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.28em] text-blue-200">
                <Store className="h-4 w-4" />
                Selected Branch
              </div>
              <h3 className="mt-3 text-2xl font-semibold">{selectedBranch.name}</h3>
              <div className="mt-5 space-y-3 text-sm text-slate-200">
                <div className="flex gap-3">
                  <MapPin className="mt-0.5 h-4 w-4 flex-none" />
                  <div>
                    <div>{selectedBranch.address || "ยังไม่ได้ระบุที่อยู่"}</div>
                    {selectedBranch.landmark ? <div className="mt-1 text-slate-400">จุดสังเกต: {selectedBranch.landmark}</div> : null}
                  </div>
                </div>
                <div className="flex gap-3">
                  <Phone className="mt-0.5 h-4 w-4 flex-none" />
                  <div>{selectedBranch.phone || "ยังไม่ได้ระบุเบอร์โทร"}</div>
                </div>
                <div className="flex gap-3">
                  <Navigation className="mt-0.5 h-4 w-4 flex-none" />
                  <div>
                    {selectedBranch.latitude !== null && selectedBranch.longitude !== null
                      ? `${selectedBranch.latitude}, ${selectedBranch.longitude}`
                      : "ยังไม่ได้ระบุพิกัด"}
                  </div>
                </div>
                <div className="rounded-2xl bg-white/10 p-4 text-slate-100">{todayWorkingHours(selectedBranch)}</div>
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                {selectedBranch.google_maps_url ? (
                  <a href={selectedBranch.google_maps_url} target="_blank" rel="noreferrer" className="rounded-full bg-white px-4 py-2 text-sm font-medium text-slate-900">
                    เปิดใน Google Maps
                  </a>
                ) : null}
                <Link to={businessSlug ? `/${businessSlug}/admin` : "/login"} className="rounded-full border border-white/25 px-4 py-2 text-sm font-medium text-white">
                  สำหรับพนักงาน
                </Link>
              </div>
            </div>
          ) : null}
        </aside>
      </section>
    </main>
  );
}

function PublicPageState({ kind, onRetry }: { kind: "loading" | "offline" | "error"; onRetry: () => void }): JSX.Element {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-2xl">
        <SystemState kind={kind} onAction={kind === "loading" ? undefined : onRetry} />
      </div>
    </main>
  );
}

function Capability({ active, label }: { active: boolean; label: string }): JSX.Element {
  return (
    <div className={`rounded-xl border px-3 py-2 font-medium ${active ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-white text-slate-500"}`}>
      {active ? "เปิดใช้" : "ยังไม่เปิด"} · {label}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4">
      <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}
