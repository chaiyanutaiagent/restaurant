import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  Check,
  ChefHat,
  Coffee,
  ConciergeBell,
  MapPin,
  Plus,
  ShoppingBag,
  Trash2,
  UtensilsCrossed,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { fbApi } from "@/lib/fbApi";
import { useAuthStore } from "@/stores/auth.store";

type QueueReset = "daily" | "per_shift";

type TableZoneDraft = {
  id: string;
  zone_name: string;
  table_count: number;
  table_name_prefix: string;
  table_capacity: number;
};

type WizardState = {
  has_tables: boolean;
  table_zones: TableZoneDraft[];
  table_qr_enabled: boolean;
  bill_at_table: boolean;
  queue_reset: QueueReset;
  queue_prefix: string;
  pickup_display_enabled: boolean;
  kitchen_stations: string[];
};

const DEFAULT_STATIONS = ["อาหาร", "เครื่องดื่มร้อน", "เครื่องดื่มเย็น"];
const STANDARD_STATIONS = ["อาหาร", "เครื่องดื่มร้อน", "เครื่องดื่มเย็น", "ขนมอบ", "ของหวาน", "Bar"];

const STEPS = [
  { id: "store", label: "รูปแบบร้าน" },
  { id: "service", label: "การขาย" },
  { id: "kitchen", label: "ครัว" },
  { id: "confirm", label: "ยืนยัน" },
];

function createTableZone(index: number): TableZoneDraft {
  const prefix = index <= 26 ? String.fromCharCode(64 + index) : `Z${index}`;
  return {
    id: `zone-${Date.now()}-${index}`,
    zone_name: index === 1 ? "โซนหลัก" : `โซน ${index}`,
    table_count: index === 1 ? 10 : 5,
    table_name_prefix: prefix,
    table_capacity: 4,
  };
}

function getTableZoneError(zones: TableZoneDraft[]): string | null {
  if (zones.length < 1) return "กรุณาเพิ่มอย่างน้อย 1 โซน";
  if (zones.length > 20) return "เพิ่มได้ไม่เกิน 20 โซน";

  const zoneNames = new Set<string>();
  const tableNames = new Set<string>();
  let totalTables = 0;

  for (const zone of zones) {
    const zoneName = zone.zone_name.trim().replace(/\s+/g, " ");
    const prefix = zone.table_name_prefix.trim().replace(/\s+/g, " ");
    if (!zoneName) return "กรุณากรอกชื่อโซนให้ครบ";
    if (!prefix) return `กรุณากรอกคำนำหน้าชื่อโต๊ะของ ${zoneName}`;
    if (!Number.isInteger(zone.table_count) || zone.table_count < 1 || zone.table_count > 100) {
      return `จำนวนโต๊ะของ ${zoneName} ต้องอยู่ระหว่าง 1 ถึง 100`;
    }
    if (!Number.isInteger(zone.table_capacity) || zone.table_capacity < 1 || zone.table_capacity > 100) {
      return `จำนวนที่นั่งของ ${zoneName} ต้องอยู่ระหว่าง 1 ถึง 100`;
    }

    const zoneKey = zoneName.toLocaleLowerCase();
    if (zoneNames.has(zoneKey)) return `ชื่อโซน "${zoneName}" ซ้ำกัน`;
    zoneNames.add(zoneKey);
    totalTables += zone.table_count;

    for (let index = 1; index <= zone.table_count; index += 1) {
      const tableName = `${prefix} ${index}`;
      const tableKey = tableName.toLocaleLowerCase();
      if (tableNames.has(tableKey)) {
        return `ชื่อโต๊ะ "${tableName}" ซ้ำกัน กรุณาเปลี่ยนคำนำหน้าชื่อโต๊ะ`;
      }
      tableNames.add(tableKey);
    }
  }

  if (totalTables > 100) return "จำนวนโต๊ะรวมทุกโซนต้องไม่เกิน 100 โต๊ะ";
  return null;
}

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง";
}

export default function FBSetupWizard(): JSX.Element {
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const branchId = useAuthStore((state) => state.branchId);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<WizardState>(() => ({
    has_tables: false,
    table_zones: [createTableZone(1)],
    table_qr_enabled: true,
    bill_at_table: true,
    queue_reset: "daily",
    queue_prefix: "",
    pickup_display_enabled: true,
    kitchen_stations: [...DEFAULT_STATIONS],
  }));

  const settingsQuery = useQuery({
    queryKey: ["branch-settings", branchId],
    queryFn: async () => (await fbApi.settings()).data.data,
    enabled: Boolean(branchId),
  });

  useEffect(() => {
    if (settingsQuery.data?.fb_setup_completed) {
      navigate("/restaurant", { replace: true });
    }
  }, [navigate, settingsQuery.data?.fb_setup_completed]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!branchId) throw new Error("ไม่พบสาขา");
      return (
        await fbApi.setup({
          has_tables: form.has_tables,
          table_zones: form.has_tables
            ? form.table_zones.map((zone) => ({
                zone_name: zone.zone_name.trim(),
                table_count: zone.table_count,
                table_name_prefix: zone.table_name_prefix.trim(),
                table_capacity: zone.table_capacity,
              }))
            : [],
          table_qr_enabled: form.has_tables && form.table_qr_enabled,
          bill_at_table: form.has_tables && form.bill_at_table,
          queue_reset: form.queue_reset,
          queue_prefix: form.queue_prefix.trim(),
          pickup_display_enabled: form.pickup_display_enabled,
          kitchen_stations: form.kitchen_stations.filter(Boolean),
        })
      ).data.data;
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["branch-settings"] });
      await queryClient.invalidateQueries({ queryKey: ["dining-tables"] });
      toast({
        title: "ตั้งค่า F&B เสร็จสมบูรณ์",
        description: form.has_tables
          ? `พร้อมใช้งาน ${result.tables_ready} โต๊ะ และรับออเดอร์กลับบ้าน`
          : "พร้อมรับออเดอร์กลับบ้านและเรียกคิว",
      });
      navigate("/restaurant", { replace: true });
    },
    onError: (error) => {
      toast({
        title: "ตั้งค่าไม่สำเร็จ",
        description: getErrorMessage(error),
        variant: "destructive",
      });
    },
  });

  function set<K extends keyof WizardState>(key: K, value: WizardState[K]): void {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateTableZone<K extends keyof Omit<TableZoneDraft, "id">>(
    id: string,
    key: K,
    value: TableZoneDraft[K],
  ): void {
    setForm((current) => ({
      ...current,
      table_zones: current.table_zones.map((zone) =>
        zone.id === id ? { ...zone, [key]: value } : zone,
      ),
    }));
  }

  function addTableZone(): void {
    setForm((current) => ({
      ...current,
      table_zones: [
        ...current.table_zones,
        createTableZone(current.table_zones.length + 1),
      ],
    }));
  }

  function removeTableZone(id: string): void {
    setForm((current) => ({
      ...current,
      table_zones: current.table_zones.filter((zone) => zone.id !== id),
    }));
  }

  function toggleStation(name: string): void {
    setForm((current) => ({
      ...current,
      kitchen_stations: current.kitchen_stations.includes(name)
        ? current.kitchen_stations.filter((station) => station !== name)
        : [...current.kitchen_stations, name],
    }));
  }

  function canContinue(): boolean {
    if (step !== 0 || !form.has_tables) return true;
    return getTableZoneError(form.table_zones) === null;
  }

  const totalTables = form.table_zones.reduce(
    (total, zone) => total + (Number.isInteger(zone.table_count) ? zone.table_count : 0),
    0,
  );
  const tableZoneError = form.has_tables ? getTableZoneError(form.table_zones) : null;

  if (settingsQuery.isLoading || settingsQuery.data?.fb_setup_completed) {
    return <div className="p-8 text-center text-slate-500">กำลังโหลด...</div>;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-orange-50 to-amber-50 p-4">
      <div className="w-full max-w-4xl">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-orange-500 shadow-lg">
            <UtensilsCrossed className="h-8 w-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">เริ่มต้นใช้งาน F&B POS</h1>
          <p className="mt-1 text-slate-500">ระบบเดียวสำหรับร้านมีโต๊ะและร้านรับกลับบ้าน</p>
        </div>

        <div className="mb-8 flex items-center justify-between">
          {STEPS.map((item, index) => (
            <div key={item.id} className="flex flex-1 items-center">
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold transition-all ${
                    index < step
                      ? "bg-orange-500 text-white"
                      : index === step
                        ? "border-2 border-orange-500 bg-white text-orange-600"
                        : "border-2 border-slate-200 bg-white text-slate-400"
                  }`}
                >
                  {index < step ? <Check className="h-4 w-4" /> : index + 1}
                </div>
                <span className={`mt-1 hidden text-xs sm:block ${index === step ? "font-medium text-orange-600" : "text-slate-400"}`}>
                  {item.label}
                </span>
              </div>
              {index < STEPS.length - 1 ? (
                <div className={`mx-1 h-0.5 flex-1 ${index < step ? "bg-orange-400" : "bg-slate-200"}`} />
              ) : null}
            </div>
          ))}
        </div>

        <div className="rounded-3xl border border-white bg-white p-6 shadow-xl sm:p-8">
          {step === 0 ? (
            <div>
              <h2 className="text-xl font-semibold text-slate-900">ร้านมีโต๊ะให้ลูกค้านั่งหรือไม่?</h2>
              <p className="mt-1 text-sm text-slate-500">ทุกร้านสามารถรับออเดอร์กลับบ้านได้เสมอ</p>
              <div className="mt-6 grid gap-4 sm:grid-cols-2">
                {[
                  {
                    value: true,
                    icon: <ConciergeBell className="h-6 w-6" />,
                    title: "มีโต๊ะให้นั่ง",
                    description: "เปิดโต๊ะ สั่งที่โต๊ะ และสั่งกลับบ้าน",
                  },
                  {
                    value: false,
                    icon: <ShoppingBag className="h-6 w-6" />,
                    title: "ไม่มีโต๊ะ",
                    description: "รับออเดอร์กลับบ้านและเรียกเลขคิว",
                  },
                ].map((option) => (
                  <button
                    key={String(option.value)}
                    type="button"
                    onClick={() => set("has_tables", option.value)}
                    className={`rounded-2xl border-2 p-5 text-left transition ${
                      form.has_tables === option.value
                        ? "border-orange-400 bg-orange-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <div className={`inline-flex rounded-xl p-2 ${form.has_tables === option.value ? "bg-orange-500 text-white" : "bg-slate-100 text-slate-500"}`}>
                      {option.icon}
                    </div>
                    <p className="mt-4 font-semibold text-slate-900">{option.title}</p>
                    <p className="mt-1 text-sm text-slate-500">{option.description}</p>
                  </button>
                ))}
              </div>

              {form.has_tables ? (
                <div className="mt-6 rounded-2xl border border-orange-200 bg-orange-50 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 font-semibold text-orange-900">
                        <MapPin className="h-5 w-5" />
                        กำหนดโซนและโต๊ะ
                      </div>
                      <p className="mt-1 text-xs text-orange-700">
                        แต่ละโซนกำหนดจำนวนโต๊ะและจำนวนที่นั่งต่างกันได้
                      </p>
                    </div>
                    <div className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-orange-800 shadow-sm">
                      {form.table_zones.length} โซน · {totalTables} โต๊ะ
                    </div>
                  </div>

                  <div className="mt-4 space-y-3">
                    {form.table_zones.map((zone, zoneIndex) => (
                      <div key={zone.id} className="rounded-2xl border border-orange-200 bg-white p-4 shadow-sm">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-orange-100 text-xs text-orange-700">
                              {zoneIndex + 1}
                            </span>
                            โซนโต๊ะ
                          </div>
                          <button
                            type="button"
                            className="inline-flex h-8 items-center gap-1 rounded-lg px-2 text-xs text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-35"
                            disabled={form.table_zones.length === 1}
                            onClick={() => removeTableZone(zone.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            ลบโซน
                          </button>
                        </div>

                        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                          <div>
                            <Label>ชื่อโซน</Label>
                            <Input
                              className="mt-1 bg-white"
                              maxLength={100}
                              placeholder="เช่น ห้องแอร์"
                              value={zone.zone_name}
                              onChange={(event) =>
                                updateTableZone(zone.id, "zone_name", event.target.value)
                              }
                            />
                          </div>
                          <div>
                            <Label>คำนำหน้าชื่อโต๊ะ</Label>
                            <Input
                              className="mt-1 bg-white"
                              maxLength={40}
                              placeholder="เช่น A"
                              value={zone.table_name_prefix}
                              onChange={(event) =>
                                updateTableZone(zone.id, "table_name_prefix", event.target.value)
                              }
                            />
                          </div>
                          <div>
                            <Label>จำนวนโต๊ะ</Label>
                            <Input
                              className="mt-1 bg-white"
                              type="number"
                              min={1}
                              max={100}
                              value={zone.table_count}
                              onChange={(event) =>
                                updateTableZone(zone.id, "table_count", Number(event.target.value))
                              }
                            />
                          </div>
                          <div>
                            <Label>ที่นั่งต่อโต๊ะ</Label>
                            <Input
                              className="mt-1 bg-white"
                              type="number"
                              min={1}
                              max={100}
                              value={zone.table_capacity}
                              onChange={(event) =>
                                updateTableZone(zone.id, "table_capacity", Number(event.target.value))
                              }
                            />
                          </div>
                        </div>
                        <p className="mt-3 text-xs text-slate-500">
                          ตัวอย่าง: {zone.table_name_prefix.trim() || "โต๊ะ"} 1 ถึง{" "}
                          {zone.table_name_prefix.trim() || "โต๊ะ"} {Math.max(zone.table_count || 0, 1)}
                          {" "}· {zone.table_capacity || 0} ที่นั่งต่อโต๊ะ
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <Button
                      type="button"
                      variant="outline"
                      className="border-orange-300 bg-white text-orange-700 hover:bg-orange-100"
                      disabled={form.table_zones.length >= 20}
                      onClick={addTableZone}
                    >
                      <Plus className="mr-2 h-4 w-4" />
                      เพิ่มโซนโต๊ะ
                    </Button>
                    {tableZoneError ? (
                      <p className="text-xs font-medium text-red-600">{tableZoneError}</p>
                    ) : (
                      <p className="text-xs text-orange-700">สร้างได้รวมสูงสุด 100 โต๊ะ</p>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {step === 1 ? (
            <div className="space-y-5">
              <div>
                <h2 className="text-xl font-semibold text-slate-900">ตั้งค่าการขาย</h2>
                <p className="mt-1 text-sm text-slate-500">ออเดอร์กลับบ้านและเลขคิวเปิดใช้งานอัตโนมัติ</p>
              </div>

              <div className="rounded-2xl border border-blue-200 bg-blue-50 p-5">
                <div className="flex items-center gap-2 font-semibold text-blue-900">
                  <ShoppingBag className="h-5 w-5" />
                  กลับบ้าน / รับที่เคาน์เตอร์
                </div>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label>Prefix คิว</Label>
                    <Input
                      className="mt-1 bg-white"
                      placeholder="เช่น Q"
                      maxLength={10}
                      value={form.queue_prefix}
                      onChange={(event) => set("queue_prefix", event.target.value)}
                    />
                    <p className="mt-1 text-xs text-blue-700">ตัวอย่าง {form.queue_prefix || ""}001</p>
                  </div>
                  <div>
                    <Label>เริ่มเลขคิวใหม่</Label>
                    <div className="mt-1 grid grid-cols-2 gap-2">
                      {(["daily", "per_shift"] as QueueReset[]).map((value) => (
                        <button
                          key={value}
                          type="button"
                          onClick={() => set("queue_reset", value)}
                          className={`rounded-lg border px-3 py-2 text-sm ${
                            form.queue_reset === value
                              ? "border-blue-500 bg-blue-100 text-blue-700"
                              : "border-slate-200 bg-white text-slate-600"
                          }`}
                        >
                          {value === "daily" ? "รายวัน" : "รายกะ"}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                <label className="mt-4 flex items-center justify-between gap-4 rounded-xl border border-blue-200 bg-white px-4 py-3">
                  <div>
                    <p className="font-medium text-slate-800">หน้าจอเรียกคิว</p>
                    <p className="text-xs text-slate-500">แสดงเลขคิวพร้อมรับบน TV หรือ tablet</p>
                  </div>
                  <input
                    type="checkbox"
                    className="h-5 w-5 accent-blue-500"
                    checked={form.pickup_display_enabled}
                    onChange={(event) => set("pickup_display_enabled", event.target.checked)}
                  />
                </label>
              </div>

              {form.has_tables ? (
                <div className="rounded-2xl border border-orange-200 bg-orange-50 p-5">
                  <div className="font-semibold text-orange-900">บริการที่โต๊ะ</div>
                  <div className="mt-4 space-y-3">
                    <SetupToggle
                      label="QR ประจำโต๊ะ"
                      description="ลูกค้าสแกน QR เพื่อดูเมนูและสั่งอาหาร"
                      checked={form.table_qr_enabled}
                      onChange={(value) => set("table_qr_enabled", value)}
                    />
                    <SetupToggle
                      label="ขอบิลจาก QR"
                      description="ให้ลูกค้ากดเรียกพนักงานเก็บเงินได้"
                      checked={form.bill_at_table}
                      onChange={(value) => set("bill_at_table", value)}
                    />
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {step === 2 ? (
            <div>
              <h2 className="text-xl font-semibold text-slate-900">เลือกส่วนครัว</h2>
              <p className="mt-1 text-sm text-slate-500">ออเดอร์จะถูกแยกไปยัง station ที่เกี่ยวข้อง</p>
              <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
                {STANDARD_STATIONS.map((name) => {
                  const active = form.kitchen_stations.includes(name);
                  const isDrink = name.includes("เครื่องดื่ม") || name === "Bar";
                  return (
                    <button
                      key={name}
                      type="button"
                      onClick={() => toggleStation(name)}
                      className={`flex flex-col items-center gap-2 rounded-2xl border-2 px-4 py-5 ${
                        active
                          ? "border-orange-400 bg-orange-50 text-orange-700"
                          : "border-slate-200 text-slate-500 hover:border-slate-300"
                      }`}
                    >
                      {isDrink ? <Coffee className="h-5 w-5" /> : <ChefHat className="h-5 w-5" />}
                      <span className="text-center text-sm font-medium">{name}</span>
                      {active ? <Check className="h-4 w-4 text-orange-500" /> : null}
                    </button>
                  );
                })}
              </div>
              <div className="mt-4">
                <Label>เพิ่ม station เอง แล้วกด Enter</Label>
                <Input
                  className="mt-1"
                  placeholder="เช่น Sushi Bar"
                  onKeyDown={(event) => {
                    if (event.key !== "Enter") return;
                    event.preventDefault();
                    const input = event.currentTarget;
                    const value = input.value.trim();
                    if (value && !form.kitchen_stations.includes(value)) {
                      setForm((current) => ({
                        ...current,
                        kitchen_stations: [...current.kitchen_stations, value],
                      }));
                      input.value = "";
                    }
                  }}
                />
              </div>
            </div>
          ) : null}

          {step === 3 ? (
            <div>
              <h2 className="text-xl font-semibold text-slate-900">ตรวจสอบก่อนเริ่มใช้งาน</h2>
              <div className="mt-6 space-y-3 rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm">
                <SummaryRow
                  label="รูปแบบร้าน"
                  value={form.has_tables ? "มีโต๊ะ + รับกลับบ้าน" : "ไม่มีโต๊ะ — รับกลับบ้าน"}
                />
                {form.has_tables ? (
                  <>
                    <SummaryRow
                      label="พื้นที่โต๊ะ"
                      value={`${form.table_zones.length} โซน · รวม ${totalTables} โต๊ะ`}
                    />
                    {form.table_zones.map((zone) => (
                      <SummaryRow
                        key={zone.id}
                        label={zone.zone_name.trim() || "ยังไม่ตั้งชื่อโซน"}
                        value={`${zone.table_count} โต๊ะ · ${zone.table_capacity} ที่นั่งต่อโต๊ะ · ${zone.table_name_prefix.trim() || "โต๊ะ"} 1–${zone.table_count}`}
                      />
                    ))}
                    <SummaryRow label="QR ประจำโต๊ะ" value={form.table_qr_enabled ? "เปิด" : "ปิด"} />
                  </>
                ) : null}
                <SummaryRow
                  label="เลขคิว"
                  value={`${form.queue_prefix || "(ไม่มี prefix)"}001 · เริ่มใหม่${form.queue_reset === "daily" ? "รายวัน" : "รายกะ"}`}
                />
                <SummaryRow label="หน้าจอเรียกคิว" value={form.pickup_display_enabled ? "เปิด" : "ปิด"} />
                <SummaryRow
                  label="Kitchen Stations"
                  value={form.kitchen_stations.length > 0 ? form.kitchen_stations.join(", ") : "ยังไม่เลือก"}
                />
              </div>
              <div className="mt-4 rounded-2xl border border-orange-200 bg-orange-50 p-4 text-sm text-orange-800">
                เปลี่ยนรูปแบบร้านและเพิ่มโต๊ะภายหลังได้จากเมนูตั้งค่า F&B
              </div>
            </div>
          ) : null}

          <div className="mt-8 flex items-center justify-between">
            <Button variant="outline" onClick={() => setStep((current) => current - 1)} disabled={step === 0}>
              ย้อนกลับ
            </Button>
            {step < STEPS.length - 1 ? (
              <Button
                className="bg-orange-500 hover:bg-orange-600"
                disabled={!canContinue()}
                onClick={() => setStep((current) => current + 1)}
              >
                ถัดไป →
              </Button>
            ) : (
              <Button
                className="bg-orange-500 hover:bg-orange-600"
                disabled={saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
              >
                {saveMutation.isPending ? "กำลังสร้างพื้นที่ร้าน..." : "เริ่มใช้งาน F&B"}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SetupToggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}): JSX.Element {
  return (
    <label className="flex items-center justify-between gap-4 rounded-xl border border-orange-200 bg-white px-4 py-3">
      <div>
        <p className="font-medium text-slate-800">{label}</p>
        <p className="text-xs text-slate-500">{description}</p>
      </div>
      <input
        type="checkbox"
        className="h-5 w-5 accent-orange-500"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-800">{value}</span>
    </div>
  );
}
