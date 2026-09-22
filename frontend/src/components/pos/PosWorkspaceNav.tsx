import {
  ChefHat,
  ClipboardList,
  Clock3,
  FileClock,
  MonitorCog,
  QrCode,
  ShoppingBag,
  Store,
  Truck,
  UsersRound,
  UtensilsCrossed,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth.store";

type PosWorkspaceNavProps = {
  mode?: "restaurant" | "retail";
  heldBillCount?: number;
  holdEnabled?: boolean;
  onHeldBills?: () => void;
  onBillCenter?: () => void;
  onShift?: () => void;
  onDeviceStatus?: () => void;
  onNavigate?: (path: string, label: string) => void;
};

type WorkspaceItem = {
  label: string;
  path: string;
  icon: typeof Store;
  active: (pathname: string, search: string) => boolean;
  visible: boolean;
};

export default function PosWorkspaceNav({
  mode = "restaurant",
  heldBillCount,
  holdEnabled = true,
  onHeldBills,
  onBillCenter,
  onShift,
  onDeviceStatus,
  onNavigate,
}: PosWorkspaceNavProps): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const canCreatePosSale = hasPermission("pos.sale.create");
  const canCreateRestaurantOrder = hasPermission("fb.order.create");
  const canManageRestaurantTables = hasPermission("fb.table.manage");
  const canViewKitchen = hasPermission("fb.kitchen.ticket.manage") || hasPermission("fb.kitchen.manage");
  const canViewCustomers = hasPermission("pos.sale.view");

  const items: WorkspaceItem[] = [
    {
      label: "ขายหน้าร้าน",
      path: "/pos",
      icon: Store,
      active: (pathname, search) => pathname === "/pos" && new URLSearchParams(search).get("channel") !== "takeaway",
      visible: canCreatePosSale,
    },
    {
      label: "เปิดโต๊ะ + QR",
      path: "/restaurant/tables",
      icon: UtensilsCrossed,
      active: (pathname) => pathname === "/restaurant/tables",
      visible: canManageRestaurantTables,
    },
    {
      label: "รับกลับ",
      path: canCreatePosSale ? "/pos?channel=takeaway" : "/restaurant/wap/legacy",
      icon: ShoppingBag,
      active: (pathname, search) => pathname === "/restaurant/wap/legacy"
        || (pathname === "/pos" && new URLSearchParams(search).get("channel") === "takeaway"),
      visible: canCreateRestaurantOrder,
    },
    {
      label: "ศูนย์ออเดอร์",
      path: "/restaurant/orders",
      icon: QrCode,
      active: (pathname) => pathname === "/restaurant/orders" || pathname.startsWith("/restaurant/session/"),
      visible: canCreateRestaurantOrder,
    },
    {
      label: "KDS",
      path: "/restaurant/kitchen",
      icon: ChefHat,
      active: (pathname) => pathname === "/restaurant/kitchen",
      visible: canViewKitchen,
    },
    {
      label: "ลูกค้า",
      path: "/crm",
      icon: UsersRound,
      active: (pathname) => pathname === "/crm",
      visible: canViewCustomers,
    },
  ];

  function open(path: string, label: string): void {
    if (onNavigate) {
      onNavigate(path, label);
      return;
    }
    navigate(path);
  }

  if (mode === "retail") {
    const retailItems = [
      { label: "ขาย", icon: Store, onClick: () => open("/pos", "ขาย") },
      {
        label: holdEnabled ? `พักบิล ${heldBillCount ?? 0}` : "พักบิลยังไม่พร้อม",
        icon: ClipboardList,
        onClick: holdEnabled ? onHeldBills : undefined,
      },
      { label: "บิล / คืนสินค้า", icon: FileClock, onClick: onBillCenter },
      { label: "กะ", icon: Clock3, onClick: onShift },
      { label: "สถานะเครื่อง", icon: MonitorCog, onClick: onDeviceStatus },
    ];
    return (
      <nav data-testid="retail-pos-workspace-bar" aria-label="พื้นที่ทำงาน Retail POS" className="shrink-0 border-b border-blue-100 bg-white px-3 py-2 text-slate-900 shadow-sm">
        <div className="flex items-center gap-2 overflow-x-auto">
          {retailItems.map((item, index) => {
            const Icon = item.icon;
            const isActive = index === 0 && location.pathname === "/pos";
            return (
              <button
                key={item.label}
                type="button"
                disabled={!item.onClick}
                aria-current={isActive ? "page" : undefined}
                onClick={item.onClick}
                className={`flex min-h-12 shrink-0 items-center gap-2 rounded-xl px-4 py-2 text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${isActive ? "bg-blue-600 font-semibold text-white shadow-sm" : "font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700"}`}
              >
                <Icon className="h-5 w-5" /> {item.label}
              </button>
            );
          })}
        </div>
      </nav>
    );
  }

  return (
    <nav data-testid="pos-workspace-bar" aria-label="พื้นที่ทำงาน POS" className="shrink-0 border-b border-slate-800 bg-slate-950 px-3 py-2 text-white">
      <div className="flex items-center gap-2 overflow-x-auto">
        <span className="hidden shrink-0 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400 xl:block">
          ช่องทางขาย
        </span>
        {items.slice(0, 3).filter((item) => item.visible).map((item) => {
          const Icon = item.icon;
          const isActive = item.active(location.pathname, location.search);
          return (
            <button
              key={item.path}
              type="button"
              aria-current={isActive ? "page" : undefined}
              onClick={() => open(item.path, item.label)}
              className={`flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm transition ${isActive ? "bg-emerald-500 font-semibold text-white" : "bg-slate-800 font-medium text-slate-100 hover:bg-slate-700"}`}
            >
              <Icon className="h-4 w-4" /> {item.label}
            </button>
          );
        })}
        <button
          type="button"
          disabled
          title="Restaurant Phase 5 ยังไม่มีออเดอร์เดลิเวอรี ปุ่มนี้จึงยังไม่เปิดใช้"
          className="flex min-h-11 shrink-0 cursor-not-allowed items-center gap-2 rounded-xl border border-slate-700 px-3 py-2 text-sm font-medium text-slate-500"
        >
          <Truck className="h-4 w-4" /> เดลิเวอรี (รอเปิดใช้)
        </button>
        <span className="mx-1 h-7 w-px shrink-0 bg-slate-700" aria-hidden="true" />
        {onHeldBills ? (
          <button
            type="button"
            onClick={onHeldBills}
            className="flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            <ClipboardList className="h-4 w-4" /> พักบิล {heldBillCount ?? 0}
          </button>
        ) : null}
        {items.slice(3).filter((item) => item.visible).map((item) => {
          const Icon = item.icon;
          const isActive = item.active(location.pathname, location.search);
          return (
            <button
              key={item.path}
              type="button"
              aria-current={isActive ? "page" : undefined}
              onClick={() => open(item.path, item.label)}
              className={`flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm transition ${isActive ? "bg-emerald-500 font-semibold text-white" : "font-medium text-slate-200 hover:bg-slate-800"}`}
            >
              <Icon className="h-4 w-4" /> {item.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
