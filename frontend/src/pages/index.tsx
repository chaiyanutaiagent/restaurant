import type { ReactElement } from "react";
import { PLATFORM_BRAND } from "@/config/platformBrand";

export default function IndexPage(): ReactElement {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl items-center justify-center px-6 py-16">
      <section className="w-full rounded-3xl border border-white/10 bg-white/10 p-10 shadow-2xl backdrop-blur">
        <p className="text-sm uppercase tracking-[0.3em] text-blue-200">Thailand ERP + POS</p>
        <h1 className="mt-4 text-4xl font-semibold text-white md:text-6xl">
          {PLATFORM_BRAND.productName} Platform - Ready
        </h1>
        <p className="mt-6 max-w-2xl text-base text-slate-200 md:text-lg">
          Multi-tenant ERP, shared operations, Restaurant, Retail, Takeaway and Hotel
          module foundation.
        </p>
      </section>
    </main>
  );
}
