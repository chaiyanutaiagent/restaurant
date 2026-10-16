import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { tenantHost } from "@/config/tenantHost";
import { useAuthStore } from "@/stores/auth.store";

export default function TenantHostBoundary({ children }: { children: ReactNode }): JSX.Element {
  const tenant = tenantHost(window.location.hostname);
  const { pathname } = useLocation();
  const companyId = useAuthStore((state) => state.companyId);
  const clearSession = useAuthStore((state) => state.clearSession);
  if (!tenant) return <>{children}</>;
  const wrongCompany = Boolean(companyId && companyId !== tenant.companyId);
  const platformRoute = pathname === "/platform" || pathname.startsWith("/platform/");
  return <>
    <div role="status" className="sticky top-0 z-[110] bg-amber-200 px-3 py-2 text-center text-sm font-semibold text-amber-950">
      SKETCH BIZ · UAT — ระบบทดสอบ บันทึกลงข้อมูลทดสอบเท่านั้น ยังไม่ใช่ Production
    </div>
    {wrongCompany || platformRoute ? <main className="mx-auto max-w-lg space-y-4 p-8 text-center">
      <h1 className="text-xl font-bold">โดเมนนี้สำหรับบริษัท สเก็ตช์ บีซ จำกัด เท่านั้น</h1>
      <p>กรุณาเข้าสู่ระบบด้วยบัญชีพนักงานของบริษัท ไม่ใช่บัญชี Platform</p>
      <button className="rounded-lg bg-blue-600 px-4 py-2 text-white" onClick={() => {
        clearSession();
        window.location.assign(`/${tenant.slug}/login`);
      }}>กลับไปเข้าสู่ระบบบริษัท</button>
    </main> : children}
  </>;
}
