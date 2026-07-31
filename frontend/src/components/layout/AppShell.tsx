import { Outlet, useLocation } from "react-router-dom";
import { useState } from "react";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";

type AppShellProps = {
  workspace?: "admin" | "restaurant";
};

const titleMap: Record<string, string> = {
  "/admin": "ERP Admin",
  "/dashboard": "Dashboard",
  "/users": "ผู้ใช้งาน",
  "/roles": "บทบาทและสิทธิ์",
  "/branches": "สาขา",
  "/403": "ไม่มีสิทธิ์เข้าถึง",
  "/pos/admin": "POS Admin",
  "/restaurant": "ภาพรวมร้านอาหาร",
  "/restaurant/admin": "Restaurant Admin",
  "/restaurant/brands": "แบรนด์ร้านอาหาร",
  "/restaurant/wap": "ขายหน้าร้าน / กลับบ้าน",
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

  const title = titleMap[location.pathname] ?? (workspace === "restaurant" ? "ร้านอาหาร" : "Restaurant POS");

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar workspace={workspace} isSidebarOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
      {isSidebarOpen ? (
        <button
          aria-label="Close sidebar"
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
          type="button"
        />
      ) : null}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <TopBar workspace={workspace} onMenuClick={() => setIsSidebarOpen(true)} title={title} />
        <main className="flex-1 overflow-auto p-3 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
