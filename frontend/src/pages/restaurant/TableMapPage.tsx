import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import { Bell, ConciergeBell, Copy, MapPin, MoreVertical, Pencil, Plus, Printer, QrCode, ReceiptText, ShoppingBag, Trash2, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import QRCode from "qrcode";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useConfirm } from "@/hooks/useConfirm";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";

type TableData = {
  id: string; name: string; zone: string; capacity: number; session_qr_token: string | null;
  table_type: string; status: string; is_active: boolean;
  active_session_id: string | null; queue_number: number | null;
  pending_count?: number; cooking_count?: number; ready_count?: number; served_count?: number; qr_pending_count?: number;
};

const STATUS_STYLE: Record<string, string> = {
  available: "border-emerald-200 bg-white",
  occupied: "border-amber-300 bg-amber-50",
  bill_requested: "border-sky-400 bg-sky-50 ring-2 ring-sky-200",
  cleaning: "border-slate-300 bg-slate-100",
};
const STATUS_LABEL: Record<string, string> = {
  available: "ว่าง", occupied: "มีลูกค้า", bill_requested: "เรียกบิล", cleaning: "กำลังทำความสะอาด",
};

type ApiErrorBody = {
  detail?: string;
  error?: string;
};

function getErrorMessage(error: unknown): string {
  const axiosError = error as AxiosError<ApiErrorBody>;
  return axiosError.response?.data?.detail ?? axiosError.response?.data?.error ?? (error instanceof Error ? error.message : "ไม่สามารถทำรายการได้");
}

type OpenSessionResult = {
  id: string;
  qr_token: string | null;
  queue_number: number | null;
};

type QrPrintTarget = {
  token: string;
  title: string;
  label: string;
  description: string;
};

function getQrUrl(qrToken: string): string {
  const configuredOrigin = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configuredOrigin) {
    try {
      return `${new URL(configuredOrigin).origin}/menu/${qrToken}`;
    } catch {
      // Fall back to the current web origin when the optional build-time URL is invalid.
    }
  }
  return `${window.location.origin}/menu/${qrToken}`;
}

export default function TableMapPage(): JSX.Element {
  const { toast } = useToast();
  const [confirm, confirmDialog] = useConfirm();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const branchId = useAuthStore((s) => s.branchId);
  const [addOpen, setAddOpen] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [qrTarget, setQrTarget] = useState<QrPrintTarget | null>(null);
  const [autoPrintPending, setAutoPrintPending] = useState(false);
  const [openTableDialogOpen, setOpenTableDialogOpen] = useState(false);
  const [openingTable, setOpeningTable] = useState<TableData | null>(null);
  const [takeawayDialogOpen, setTakeawayDialogOpen] = useState(false);
  const [takeawayCustomerName, setTakeawayCustomerName] = useState("");
  const [takeawayCustomerPhone, setTakeawayCustomerPhone] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [editingTable, setEditingTable] = useState<TableData | null>(null);
  const [newName, setNewName] = useState("");
  const [newZone, setNewZone] = useState("โซนทั่วไป");
  const [newCapacity, setNewCapacity] = useState("4");
  const [guestCount, setGuestCount] = useState("1");
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [editName, setEditName] = useState("");
  const [editZone, setEditZone] = useState("โซนทั่วไป");
  const [editCapacity, setEditCapacity] = useState("4");
  const [editStatus, setEditStatus] = useState("available");

  const tablesQuery = useQuery({
    queryKey: ["dining-tables", branchId],
    queryFn: async () => (await authApi.get("/restaurant/tables")).data.data as TableData[],
    refetchInterval: 15_000,
    enabled: Boolean(branchId),
  });

  useEffect(() => {
    if (!qrOpen || !qrDataUrl || !autoPrintPending) return;
    const timer = window.setTimeout(() => {
      setAutoPrintPending(false);
      window.print();
    }, 350);
    return () => window.clearTimeout(timer);
  }, [autoPrintPending, qrDataUrl, qrOpen]);

  const createMutation = useMutation({
    mutationFn: async () => {
      const name = newName.trim();
      const zone = newZone.trim();
      const capacity = Number(newCapacity);
      if (!branchId) {
        throw new Error("กรุณาเลือกสาขาก่อนเพิ่มโต๊ะ");
      }
      if (!name) {
        throw new Error("กรุณากรอกชื่อโต๊ะ");
      }
      if (!zone) {
        throw new Error("กรุณากรอกชื่อโซน");
      }
      if (!Number.isFinite(capacity) || capacity < 1) {
        throw new Error("จำนวนที่นั่งต้องมากกว่า 0");
      }
      return authApi.post("/restaurant/tables", { name, zone, capacity });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["dining-tables"] });
      toast({ title: `เพิ่มโต๊ะ "${newName.trim()}" แล้ว` });
      setAddOpen(false); setNewName(""); setNewZone("โซนทั่วไป"); setNewCapacity("4");
    },
    onError: (error) => {
      toast({
        title: "เพิ่มโต๊ะไม่สำเร็จ",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    },
  });

  const openSessionMutation = useMutation({
    mutationFn: async () => {
      const count = Number(guestCount);
      if (!openingTable) {
        throw new Error("ไม่พบโต๊ะที่ต้องการเปิด");
      }
      if (!Number.isFinite(count) || count < 1) {
        throw new Error("จำนวนลูกค้าต้องมากกว่า 0");
      }
      const response = await authApi.post("/restaurant/sessions", {
        table_id: openingTable.id,
        guest_count: count,
        customer_name: customerName.trim() || undefined,
        customer_phone: customerPhone.trim() || undefined,
      });
      return response.data.data as OpenSessionResult;
    },
    onSuccess: async (session) => {
      const table = openingTable;
      if (!table) return;
      if (!session.qr_token) {
        toast({
          title: "เปิดโต๊ะแล้ว",
          description: "สาขานี้ปิดบริการ QR ต่อรอบอยู่ จึงไม่สร้างใบ QR",
        });
        await queryClient.invalidateQueries({ queryKey: ["dining-tables"] });
        setOpenTableDialogOpen(false);
        setOpeningTable(null);
        setGuestCount("1");
        setCustomerName("");
        setCustomerPhone("");
        return;
      }
      try {
        const dataUrl = await QRCode.toDataURL(getQrUrl(session.qr_token), { width: 320, margin: 2 });
        setQrDataUrl(dataUrl);
        setQrTarget({
          token: session.qr_token,
          title: `QR รอบนี้ · โต๊ะ ${table.name}`,
          label: `โต๊ะ ${table.name}`,
          description: "ใช้ได้เฉพาะรอบเปิดโต๊ะปัจจุบัน",
        });
        setQrOpen(true);
        setAutoPrintPending(true);
        toast({ title: "เปิดโต๊ะแล้ว", description: "กำลังเปิดหน้าพิมพ์ QR สำหรับรอบนี้" });
      } catch {
        toast({
          title: "เปิดโต๊ะแล้ว แต่สร้างรูป QR ไม่สำเร็จ",
          description: "กดปุ่ม QR รอบนี้บนโต๊ะเพื่อพิมพ์อีกครั้ง",
          variant: "destructive",
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["dining-tables"] });
      setOpenTableDialogOpen(false);
      setOpeningTable(null);
      setGuestCount("1");
      setCustomerName("");
      setCustomerPhone("");
    },
    onError: (error) => {
      toast({
        title: "เปิดโต๊ะไม่สำเร็จ",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    },
  });

  const openTakeawayMutation = useMutation({
    mutationFn: async () => {
      if (!branchId) {
        throw new Error("กรุณาเลือกสาขาก่อนออก QR รับกลับ");
      }
      const response = await authApi.post("/restaurant/sessions", {
        table_id: null,
        guest_count: 1,
        customer_name: takeawayCustomerName.trim() || undefined,
        customer_phone: takeawayCustomerPhone.trim() || undefined,
      });
      return response.data.data as OpenSessionResult;
    },
    onSuccess: async (session) => {
      if (!session.qr_token) {
        toast({
          title: "เปิดคิวรับกลับแล้ว แต่ยังไม่มี QR",
          description: "กรุณาเปิด QR ต่อรอบในตั้งค่า F&B",
          variant: "destructive",
        });
        setTakeawayDialogOpen(false);
        return;
      }
      const queueLabel = session.queue_number
        ? `คิว ${String(session.queue_number).padStart(3, "0")}`
        : "ออเดอร์รับกลับ";
      try {
        const dataUrl = await QRCode.toDataURL(getQrUrl(session.qr_token), { width: 320, margin: 2 });
        setQrDataUrl(dataUrl);
        setQrTarget({
          token: session.qr_token,
          title: `QR รับกลับ · ${queueLabel}`,
          label: `รับกลับ · ${queueLabel}`,
          description: "ใช้ได้เฉพาะออเดอร์นี้และหมดอายุเมื่อปิดคิว",
        });
        setQrOpen(true);
        setAutoPrintPending(true);
        toast({ title: "เปิดคิวรับกลับแล้ว", description: "กำลังเปิดหน้าพิมพ์ QR สำหรับลูกค้า" });
      } catch {
        toast({
          title: "เปิดคิวรับกลับแล้ว แต่สร้างรูป QR ไม่สำเร็จ",
          description: "เปิดหน้าออเดอร์เพื่อดูคิวที่สร้างไว้",
          variant: "destructive",
        });
      }
      setTakeawayDialogOpen(false);
      setTakeawayCustomerName("");
      setTakeawayCustomerPhone("");
      await queryClient.invalidateQueries({ queryKey: ["restaurant-sessions"] });
    },
    onError: (error) => {
      toast({
        title: "เปิดคิวรับกลับไม่สำเร็จ",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    },
  });

  const closeSessionMutation = useMutation({
    mutationFn: async (sessionId: string) =>
      authApi.post(`/restaurant/sessions/${sessionId}/close`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["dining-tables"] });
      toast({ title: "ปิดโต๊ะแล้ว" });
    },
    onError: (error) => {
      toast({
        title: "ปิดโต๊ะไม่สำเร็จ",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    },
  });

  const updateTableMutation = useMutation({
    mutationFn: async () => {
      if (!editingTable) {
        throw new Error("ไม่พบโต๊ะที่ต้องการแก้ไข");
      }
      const name = editName.trim();
      const zone = editZone.trim();
      const capacity = Number(editCapacity);
      if (!name) {
        throw new Error("กรุณากรอกชื่อโต๊ะ");
      }
      if (!zone) {
        throw new Error("กรุณากรอกชื่อโซน");
      }
      if (!Number.isFinite(capacity) || capacity < 1) {
        throw new Error("จำนวนที่นั่งต้องมากกว่า 0");
      }
      if (editingTable.active_session_id && editStatus === "available") {
        throw new Error("โต๊ะที่มี session เปิดอยู่ไม่สามารถเปลี่ยนเป็นว่างได้");
      }
      return authApi.patch(`/restaurant/tables/${editingTable.id}`, {
        name,
        zone,
        capacity,
        status: editStatus,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["dining-tables"] });
      toast({ title: "อัปเดตโต๊ะแล้ว" });
      setEditOpen(false);
      setEditingTable(null);
    },
    onError: (error) => {
      toast({
        title: "อัปเดตโต๊ะไม่สำเร็จ",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    },
  });

  const deactivateTableMutation = useMutation({
    mutationFn: async (tableId: string) => authApi.delete(`/restaurant/tables/${tableId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["dining-tables"] });
      toast({ title: "ปิดใช้งานโต๊ะแล้ว" });
    },
    onError: (error) => {
      toast({
        title: "ปิดใช้งานโต๊ะไม่สำเร็จ",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    },
  });

  function openEdit(table: TableData): void {
    setEditingTable(table);
    setEditName(table.name);
    setEditZone(table.zone || "โซนทั่วไป");
    setEditCapacity(String(table.capacity));
    setEditStatus(table.status);
    setEditOpen(true);
  }

  function openTable(table: TableData): void {
    setOpeningTable(table);
    setGuestCount("1");
    setCustomerName("");
    setCustomerPhone("");
    setOpenTableDialogOpen(true);
  }

  async function copyQrLink(table: TableData): Promise<void> {
    if (!table.session_qr_token) {
      toast({ title: "ยังไม่มี QR สำหรับรอบนี้", description: "เปิดโต๊ะก่อน แล้วระบบจะสร้าง QR เฉพาะรอบนั้น", variant: "destructive" });
      return;
    }
    await copyQrTarget(table.session_qr_token, table.name);
  }

  async function copyQrTarget(token: string, label: string): Promise<void> {
    await navigator.clipboard.writeText(getQrUrl(token));
    toast({ title: "คัดลอกลิงก์ QR สำหรับรอบนี้แล้ว", description: label });
  }

  async function confirmDeactivate(table: TableData): Promise<void> {
    const ok = await confirm({
      title: `ปิดใช้งานโต๊ะ ${table.name}`,
      description: "โต๊ะนี้จะถูกซ่อนจากแผนที่โต๊ะ หากมี session เปิดอยู่ระบบจะไม่อนุญาตให้ปิดใช้งาน",
      confirmLabel: "ปิดใช้งาน",
      variant: "destructive",
    });
    if (ok) {
      deactivateTableMutation.mutate(table.id);
    }
  }

  async function showQr(table: TableData): Promise<void> {
    if (!table.session_qr_token) {
      toast({ title: "เปิดโต๊ะก่อนพิมพ์ QR", description: "QR สั่งอาหารจะถูกสร้างใหม่ต่อหนึ่งรอบการเปิดโต๊ะ", variant: "destructive" });
      return;
    }
    const dataUrl = await QRCode.toDataURL(getQrUrl(table.session_qr_token), { width: 320, margin: 2 });
    setQrDataUrl(dataUrl);
    setQrTarget({
      token: table.session_qr_token,
      title: `QR รอบนี้ · โต๊ะ ${table.name}`,
      label: `โต๊ะ ${table.name}`,
      description: "ใช้ได้เฉพาะรอบเปิดโต๊ะปัจจุบัน",
    });
    setAutoPrintPending(false);
    setQrOpen(true);
  }

  const tables = tablesQuery.data ?? [];
  const occupiedCount = tables.filter((table) => table.status === "occupied").length;
  const billRequestedCount = tables.filter((table) => table.status === "bill_requested").length;
  const availableCount = tables.filter((table) => table.status === "available").length;
  const qrNewOrderCount = tables.reduce((sum, table) => sum + (table.qr_pending_count ?? 0), 0);
  const tableZones = Array.from(
    tables.reduce<Map<string, TableData[]>>((groups, table) => {
      const zone = table.zone?.trim() || "โซนทั่วไป";
      const zoneTables = groups.get(zone) ?? [];
      zoneTables.push(table);
      groups.set(zone, zoneTables);
      return groups;
    }, new Map()),
  );

  return (
    <div>
      <PageHeader
        title="แผนที่โต๊ะ"
        subtitle={`${tables.filter((t) => t.status === "occupied" || t.status === "bill_requested").length} / ${tables.length} โต๊ะที่มีลูกค้า`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button className="bg-emerald-600 hover:bg-emerald-700" disabled={!branchId} onClick={() => setTakeawayDialogOpen(true)}>
              <ShoppingBag className="mr-2 h-4 w-4" /> ออก QR รับกลับ
            </Button>
            <Button className="bg-orange-500 hover:bg-orange-600" disabled={!branchId} onClick={() => setAddOpen(true)}>
              <Plus className="mr-2 h-4 w-4" /> เพิ่มโต๊ะ
            </Button>
          </div>
        }
      />

      <div className="rounded-[28px] border border-white/80 bg-white/85 p-4 shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur lg:p-6">
        {!branchId && (
          <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            กรุณาเลือกสาขาที่มุมขวาบนก่อนเพิ่มโต๊ะ
          </div>
        )}

        {tablesQuery.isError && (
          <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            โหลดข้อมูลโต๊ะไม่สำเร็จ: {getErrorMessage(tablesQuery.error)}
          </div>
        )}

        <div className="mb-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3">
            <p className="text-xs font-semibold text-emerald-700">โต๊ะว่าง</p>
            <p className="mt-1 text-2xl font-bold text-emerald-900">{availableCount}</p>
          </div>
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
            <p className="text-xs font-semibold text-amber-700">มีลูกค้า</p>
            <p className="mt-1 text-2xl font-bold text-amber-900">{occupiedCount}</p>
          </div>
          <div className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3">
            <p className="text-xs font-semibold text-sky-700">เรียกบิล</p>
            <p className="mt-1 text-2xl font-bold text-sky-900">{billRequestedCount}</p>
          </div>
        </div>
        {qrNewOrderCount > 0 ? (
          <div className="mb-5 rounded-2xl border border-orange-200 bg-orange-50 px-4 py-3 text-sm font-semibold text-orange-800">
            มีออเดอร์ใหม่จาก QR รอครัวรับ {qrNewOrderCount} รายการ
          </div>
        ) : null}

        {tables.length === 0 && !tablesQuery.isLoading && (
          <div className="rounded-2xl border border-dashed border-slate-300 p-12 text-center text-slate-400">
            <ConciergeBell className="mx-auto mb-3 h-10 w-10" />
            <p className="font-medium">ยังไม่มีโต๊ะ</p>
            <p className="mt-1 text-sm">กดปุ่ม "เพิ่มโต๊ะ" เพื่อเริ่มต้น</p>
          </div>
        )}

        <div className="space-y-8">
          {tableZones.map(([zone, zoneTables]) => (
            <section key={zone}>
              <div className="mb-3 flex items-center justify-between border-b border-slate-200 pb-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-100 text-orange-700">
                    <MapPin className="h-4 w-4" />
                  </span>
                  <div>
                    <h2 className="font-semibold text-slate-900">{zone}</h2>
                    <p className="text-xs text-slate-500">{zoneTables.length} โต๊ะ</p>
                  </div>
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
                {zoneTables.map((table) => (
            <div key={table.id} className={`rounded-2xl border-2 p-5 shadow-sm transition-all ${table.qr_pending_count ? "ring-2 ring-orange-300" : ""} ${STATUS_STYLE[table.status] ?? "border-slate-200 bg-white"}`}>
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-bold text-slate-900">{table.name}</h3>
                  <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                    <Users className="h-3 w-3" />
                    <span>{table.capacity} ที่นั่ง</span>
                  </div>
                </div>
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${
                  table.status === "available" ? "bg-emerald-100 text-emerald-700"
                  : table.status === "bill_requested" ? "bg-sky-600 text-white"
                  : "bg-amber-100 text-amber-800"
                }`}>
                  {table.status === "bill_requested" ? <Bell className="h-3 w-3" /> : null}
                  {STATUS_LABEL[table.status] ?? table.status}
                </span>
              </div>

              <div className="mt-3 flex items-center justify-end">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                      aria-label={`จัดการโต๊ะ ${table.name}`}
                    >
                      <MoreVertical className="h-4 w-4" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => openEdit(table)}>
                      <Pencil className="mr-2 h-4 w-4" />
                      แก้ไขโต๊ะ
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => void copyQrLink(table)}>
                      <Copy className="mr-2 h-4 w-4" />
                      คัดลอก QR รอบนี้
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-red-600 focus:bg-red-50 focus:text-red-700"
                      onClick={() => void confirmDeactivate(table)}
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      ปิดใช้งานโต๊ะ
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              {table.queue_number && (
                <div className="mt-3 rounded-xl bg-white/90 px-3 py-2 text-center shadow-sm">
                  <span className="text-xs text-slate-500">คิว</span>
                  <span className="ml-2 text-2xl font-bold text-slate-950">{String(table.queue_number).padStart(3, "0")}</span>
                </div>
              )}

              {table.active_session_id ? (
                <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <div className={`rounded-xl px-2 py-2 ${table.qr_pending_count ? "bg-orange-500 text-white" : "bg-white/80 text-slate-600"}`}>
                    <p className="font-semibold">QR ใหม่</p>
                    <p className="text-lg font-black">{table.qr_pending_count ?? 0}</p>
                  </div>
                  <div className="rounded-xl bg-white/80 px-2 py-2 text-slate-600">
                    <p className="font-semibold">ค้างครัว</p>
                    <p className="text-lg font-black">{(table.pending_count ?? 0) + (table.cooking_count ?? 0)}</p>
                  </div>
                  <div className={`rounded-xl px-2 py-2 ${(table.ready_count ?? 0) > 0 ? "bg-emerald-500 text-white" : "bg-white/80 text-slate-600"}`}>
                    <p className="font-semibold">พร้อมเสิร์ฟ</p>
                    <p className="text-lg font-black">{table.ready_count ?? 0}</p>
                  </div>
                </div>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => showQr(table)}
                  disabled={!table.session_qr_token}
                  className="flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  <QrCode className="h-3 w-3" /> QR รอบนี้
                </button>

                {table.status === "available" ? (
                  <button
                    type="button"
                    onClick={() => openTable(table)}
                    className="flex-1 rounded-lg bg-slate-950 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
                  >
                    เปิดโต๊ะ
                  </button>
                ) : table.active_session_id ? (
                  <>
                    <button
                      type="button"
                      onClick={() => navigate(`/restaurant/session/${table.active_session_id}/detail`)}
                      className="flex items-center gap-1 rounded-lg bg-slate-950 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
                    >
                      ดู/สั่งเพิ่ม
                    </button>
                    <button
                      type="button"
                      onClick={() => navigate(`/restaurant/session/${table.active_session_id}/checkout`)}
                      className="flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
                    >
                      <ReceiptText className="h-3 w-3" />
                      รวมบิล
                    </button>
                    <button
                      type="button"
                      onClick={() => table.active_session_id && closeSessionMutation.mutate(table.active_session_id)}
                      className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                    >
                      ปิด
                    </button>
                  </>
                ) : null}
              </div>
            </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>

      {/* Add Table Dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>เพิ่มโต๊ะใหม่</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div><Label>โซนโต๊ะ</Label><Input className="mt-1" value={newZone} onChange={(e) => setNewZone(e.target.value)} placeholder="เช่น ห้องแอร์, สวน, ชั้น 2" /></div>
            <div><Label>ชื่อโต๊ะ</Label><Input className="mt-1" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="เช่น A1, โต๊ะริมหน้าต่าง" /></div>
            <div><Label>จำนวนที่นั่ง</Label><Input type="number" className="mt-1" value={newCapacity} onChange={(e) => setNewCapacity(e.target.value)} min="1" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>ยกเลิก</Button>
            <Button className="bg-orange-500 hover:bg-orange-600" disabled={!branchId || !newZone.trim() || !newName.trim() || createMutation.isPending} onClick={() => createMutation.mutate()}>
              {createMutation.isPending ? "กำลังบันทึก..." : "เพิ่มโต๊ะ"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={takeawayDialogOpen} onOpenChange={setTakeawayDialogOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>เปิดคิวรับกลับและออก QR</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              ระบบจะเปิดออเดอร์รับกลับ ออกเลขคิว และสร้าง QR เฉพาะออเดอร์นี้ ลูกค้าสแกนแล้วส่งรายการเข้าครัวได้ทันที
            </div>
            <div>
              <Label>ชื่อลูกค้า (ถ้ามี)</Label>
              <Input className="mt-1" value={takeawayCustomerName} onChange={(e) => setTakeawayCustomerName(e.target.value)} placeholder="เช่น คุณสมชาย" />
            </div>
            <div>
              <Label>เบอร์โทร (ถ้ามี)</Label>
              <Input className="mt-1" value={takeawayCustomerPhone} onChange={(e) => setTakeawayCustomerPhone(e.target.value)} placeholder="ใช้ค้นหาหรือติดต่อลูกค้า" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTakeawayDialogOpen(false)}>ยกเลิก</Button>
            <Button className="bg-emerald-600 hover:bg-emerald-700" disabled={!branchId || openTakeawayMutation.isPending} onClick={() => openTakeawayMutation.mutate()}>
              {openTakeawayMutation.isPending ? "กำลังเปิดคิว..." : "เปิดคิวและพิมพ์ QR"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={openTableDialogOpen} onOpenChange={setOpenTableDialogOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>เปิดโต๊ะ {openingTable?.name}</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
              ระบบจะสร้าง QR ใหม่สำหรับรอบนี้และเปิดหน้าพิมพ์อัตโนมัติ QR จะหมดอายุเมื่อปิดโต๊ะ
            </div>
            <div>
              <Label>จำนวนลูกค้า</Label>
              <Input type="number" className="mt-1" value={guestCount} onChange={(e) => setGuestCount(e.target.value)} min="1" />
            </div>
            <div>
              <Label>ชื่อลูกค้า (ถ้ามี)</Label>
              <Input className="mt-1" value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="เช่น คุณสมชาย" />
            </div>
            <div>
              <Label>เบอร์โทร (ถ้ามี)</Label>
              <Input className="mt-1" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} placeholder="ใช้ติดตามหรือค้นหาออเดอร์" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenTableDialogOpen(false)}>ยกเลิก</Button>
            <Button className="bg-slate-950 hover:bg-slate-800" disabled={!openingTable || Number(guestCount) < 1 || openSessionMutation.isPending} onClick={() => openSessionMutation.mutate()}>
              {openSessionMutation.isPending ? "กำลังเปิดโต๊ะ..." : "เปิดโต๊ะและพิมพ์ QR"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>แก้ไขโต๊ะ {editingTable?.name}</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div><Label>โซนโต๊ะ</Label><Input className="mt-1" value={editZone} onChange={(e) => setEditZone(e.target.value)} /></div>
            <div><Label>ชื่อโต๊ะ</Label><Input className="mt-1" value={editName} onChange={(e) => setEditName(e.target.value)} /></div>
            <div><Label>จำนวนที่นั่ง</Label><Input type="number" className="mt-1" value={editCapacity} onChange={(e) => setEditCapacity(e.target.value)} min="1" /></div>
            <div>
              <Label>สถานะ</Label>
              <select
                className="mt-1 h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm"
                value={editStatus}
                onChange={(e) => setEditStatus(e.target.value)}
              >
                <option value="available" disabled={Boolean(editingTable?.active_session_id)}>ว่าง</option>
                <option value="occupied">มีลูกค้า</option>
                <option value="bill_requested">เรียกบิล</option>
                <option value="cleaning">กำลังทำความสะอาด</option>
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>ยกเลิก</Button>
            <Button className="bg-slate-950 hover:bg-slate-800" disabled={!editZone.trim() || !editName.trim() || updateTableMutation.isPending} onClick={() => updateTableMutation.mutate()}>
              {updateTableMutation.isPending ? "กำลังบันทึก..." : "บันทึก"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* QR Dialog */}
      <Dialog
        open={qrOpen}
        onOpenChange={(open) => {
          setQrOpen(open);
          if (!open) setAutoPrintPending(false);
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>{qrTarget?.title ?? "QR รอบนี้"}</DialogTitle></DialogHeader>
          <div className="qr-print-card rounded-2xl border border-slate-200 bg-white p-5 text-center">
            <div className="text-xs font-semibold uppercase text-slate-500">สแกนเพื่อสั่งอาหาร</div>
            <div className="mt-1 text-2xl font-bold text-slate-950">{qrTarget?.label}</div>
            <div className="mt-1 text-xs text-slate-500">{qrTarget?.description}</div>
            {qrDataUrl && <img src={qrDataUrl} alt={`QR ${qrTarget?.label ?? "สั่งอาหาร"}`} className="mx-auto mt-4 h-72 w-72 rounded-2xl" />}
            {qrTarget && (
              <div className="mt-3 break-all rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                {getQrUrl(qrTarget.token)}
              </div>
            )}
            {autoPrintPending ? (
              <div className="mt-3 text-sm font-semibold text-sky-700">กำลังเปิดหน้าพิมพ์...</div>
            ) : null}
          </div>
          <div className="qr-dialog-actions mt-4 grid grid-cols-2 gap-2">
            <Button disabled={!qrTarget} onClick={() => qrTarget && void copyQrTarget(qrTarget.token, qrTarget.label)} variant="outline">
              <Copy className="mr-2 h-4 w-4" />
              คัดลอกลิงก์
            </Button>
            <Button onClick={() => window.print()} className="bg-slate-950 hover:bg-slate-800">
              <Printer className="mr-2 h-4 w-4" />
              พิมพ์ซ้ำ
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      {confirmDialog}
    </div>
  );
}
