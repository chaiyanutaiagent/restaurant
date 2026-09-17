import { Outlet, useLocation } from "react-router-dom";
import { useState } from "react";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";
import PosWorkspaceHeader from "@/components/pos/PosWorkspaceHeader";
import PosWorkspaceNav from "@/components/pos/PosWorkspaceNav";
import { PLATFORM_BRAND } from "@/config/platformBrand";

type AppShellProps = {
  workspace?: "admin" | "restaurant";
};

const titleMap: Record<string, string> = {
  "/admin": "ERP Admin",
  "/dashboard": "Dashboard",
  "/users": "ผู้ใช้งาน",
  "/roles": "บทบาทและสิทธิ์",
  "/workspaces": "พื้นที่ทำงานของบริษัท",
  "/reports/company": "รายงานรวมบริษัท",
  "/company-kitchen": "ครัวกลางบริษัท",
  "/company-distribution": "Demand และกระจายสินค้า",
  "/branches": "สาขา",
  "/billing": "แพ็กเกจและการเรียกเก็บเงิน",
  "/privacy-support": "ความเป็นส่วนตัวและการช่วยเหลือ",
  "/settings/tax": "ตั้งค่าภาษี",
  "/tax-center": "ศูนย์ภาษี",
  "/403": "ไม่มีสิทธิ์เข้าถึง",
  "/pos/admin": "POS Admin",
  "/restaurant": "ภาพรวมร้านอาหาร",
  "/restaurant/admin": "Restaurant Admin",
  "/restaurant/brands": "แบรนด์ร้านอาหาร",
  "/restaurant/wap": "ขายหน้าร้าน / กลับบ้าน",
  "/restaurant/wap/legacy": "รับกลับ (โหมดสำรอง)",
  "/restaurant/close-shift": "ปิดกะร้านอาหาร",
  "/restaurant/tables": "แผนที่โต๊ะ",
  "/restaurant/orders": "ออเดอร์ร้านอาหาร",
  "/restaurant/recipes": "สูตรอาหาร",
  "/restaurant/qr": "QR รับออเดอร์",
  "/restaurant/settings": "ตั้งค่าร้านอาหาร",
  "/restaurant/reports/ingredients": "รายงานวัตถุดิบ"
};

export default function AppShell({ workspace = "admin" }: AppShellProps): JSX.Element {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const location = useLocation();

  const title = titleMap[location.pathname] ?? (workspace === "restaurant" ? "ร้านอาหาร" : PLATFORM_BRAND.companyAdminName);
  const isPosWorkspace = location.pathname === "/crm"
    || location.pathname === "/restaurant/tables"
    || location.pathname === "/restaurant/wap"
    || location.pathname === "/restaurant/wap/legacy"
    || location.pathname === "/restaurant/orders"
    || location.pathname.startsWith("/restaurant/session/");

  if (isPosWorkspace) {
    return (
      <div
        data-testid="pos-operation-shell"
        className="flex h-screen flex-col overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(251,191,36,0.16),_transparent_28%),linear-gradient(180deg,_#fffaf0_0%,_#f8fafc_42%,_#eef2ff_100%)]"
      >
        <PosWorkspaceHeader title={title} />
        <PosWorkspaceNav />
        <main className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto p-3 md:p-4 xl:p-5">
          <Outlet />
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-[linear-gradient(180deg,#f8fafc_0%,#eef2f7_100%)]">
      <Sidebar workspace={workspace} isSidebarOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
      {isSidebarOpen ? (
        <button
          aria-label="Close sidebar"
          className="fixed inset-0 z-40 bg-slate-950/45 backdrop-blur-sm xl:hidden"
          onClick={() => setIsSidebarOpen(false)}
          type="button"
        />
      ) : null}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <TopBar workspace={workspace} onMenuClick={() => setIsSidebarOpen(true)} title={title} />
        <main className="flex-1 overflow-auto p-3 md:p-5 xl:p-7 2xl:p-8">
          <div className="app-page">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
