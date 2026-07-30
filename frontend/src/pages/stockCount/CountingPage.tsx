import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { authApi, systemApi } from "@/lib/api";
import { formatThaiCurrency, formatThaiDate } from "@/lib/cartUtils";
import { stockApi } from "@/lib/stockApi";
import { stockCountApi } from "@/lib/stockCountApi";
import type { ApiResponse } from "@/types/api";
import type { StockLocation } from "@/types/stock";
import type { CountItem, CountSession } from "@/types/stockCount";
import type { Branch, UserBranch } from "@/types/user";
import CompleteDialog from "@/pages/stockCount/CompleteDialog";
import VarianceReportDialog from "@/pages/stockCount/VarianceReportDialog";

type ItemDraft = {
  actual_qty: string;
  note: string;
};

type FilterMode = "all" | "uncounted" | "counted" | "variance";

function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

function statusVariant(status: string): "secondary" | "default" | "success" | "destructive" {
  if (status === "completed") return "success";
  if (status === "cancelled") return "destructive";
  if (status === "in_progress") return "default";
  return "secondary";
}

export default function CountingPage(): JSX.Element {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const scanInputRef = useRef<HTMLInputElement | null>(null);
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({});
  const [drafts, setDrafts] = useState<Record<string, ItemDraft>>({});
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [scanValue, setScanValue] = useState("");
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);

  const branchesQuery = useQuery({
    queryKey: ["stock-count", "branches", "detail"],
    queryFn: async () => {
      try {
        const response = await systemApi.branches();
        return response.data as ApiResponse<Branch[]>;
      } catch {
        const fallback = await authApi.myBranches();
        return {
          data: fallback.data.data.map((item: UserBranch) => ({
            id: item.branch_id,
            company_id: "",
            code: item.branch_name,
            name: item.branch_name,
            name_en: null,
            is_warehouse: false,
            is_active: true,
            sort_order: 0
          })),
          meta: fallback.data.meta,
          error: fallback.data.error
        } satisfies ApiResponse<Branch[]>;
      }
    }
  });

  const locationsQuery = useQuery({
    queryKey: ["stock-count", "locations", "detail"],
    queryFn: async () => {
      const response = await stockApi.listLocations();
      return response.data as ApiResponse<StockLocation[]>;
    }
  });

  const sessionQuery = useQuery({
    queryKey: ["stock-count", "session", id],
    queryFn: async () => {
      const response = await stockCountApi.getSession(id);
      return response.data as ApiResponse<CountSession>;
    }
  });

  const session = sessionQuery.data?.data;
  const branchMap = useMemo(
    () => new Map((branchesQuery.data?.data ?? []).map((item) => [item.id, item.name])),
    [branchesQuery.data?.data]
  );
  const locationMap = useMemo(
    () => new Map((locationsQuery.data?.data ?? []).map((item) => [item.id, item.name])),
    [locationsQuery.data?.data]
  );

  useEffect(() => {
    if (session?.status === "in_progress") {
      scanInputRef.current?.focus();
    }
  }, [session?.status]);

  useEffect(() => {
    if (!session) {
      return;
    }
    setDrafts((current) => {
      const next = { ...current };
      for (const item of session.items) {
        next[item.id] = {
          actual_qty: item.actual_qty === null ? current[item.id]?.actual_qty ?? "" : String(item.actual_qty),
          note: item.note ?? current[item.id]?.note ?? ""
        };
      }
      return next;
    });
  }, [session]);

  const items = useMemo(() => {
    if (!session) {
      return [] as Array<CountItem & { liveActualQty: number | null; liveVarianceQty: number | null; liveNote: string }>;
    }
    return session.items
      .map((item) => {
        const draft = drafts[item.id];
        const liveActualQty = draft?.actual_qty !== undefined && draft.actual_qty !== "" ? Number(draft.actual_qty) : item.actual_qty;
        const liveVarianceQty = liveActualQty === null ? null : Number(liveActualQty) - Number(item.expected_qty);
        return {
          ...item,
          liveActualQty,
          liveVarianceQty,
          liveNote: draft?.note ?? item.note ?? ""
        };
      })
      .filter((item) => {
        if (filterMode === "uncounted") return item.liveActualQty === null;
        if (filterMode === "counted") return item.liveActualQty !== null;
        if (filterMode === "variance") return item.liveActualQty !== null && Number(item.liveVarianceQty ?? 0) !== 0;
        return true;
      });
  }, [drafts, filterMode, session]);

  const countedCount = useMemo(
    () => items.filter((item) => item.liveActualQty !== null).length,
    [items]
  );
  const overallCounted = useMemo(
    () => (session?.items ?? []).filter((item) => {
      const draft = drafts[item.id];
      return draft?.actual_qty !== undefined ? draft.actual_qty !== "" : item.actual_qty !== null;
    }).length,
    [drafts, session?.items]
  );
  const completionPercent = session?.total_items ? Math.round((overallCounted / session.total_items) * 100) : 0;

  function setItemDraft(itemId: string, field: keyof ItemDraft, value: string): void {
    setDrafts((current) => ({
      ...current,
      [itemId]: {
        actual_qty: current[itemId]?.actual_qty ?? "",
        note: current[itemId]?.note ?? "",
        [field]: value
      }
    }));
  }

  async function refreshSession(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["stock-count", "session", id] });
    await queryClient.invalidateQueries({ queryKey: ["stock-count", "sessions"] });
  }

  async function handleStart(): Promise<void> {
    try {
      await stockCountApi.startSession(id);
      toast({ title: "เริ่มนับสินค้าแล้ว" });
      await refreshSession();
    } catch (error) {
      toast({
        title: "เริ่มนับไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function handleSaveAll(): Promise<void> {
    if (!session) {
      return;
    }
    const payload = session.items
      .map((item) => ({
        item_id: item.id,
        actual_qty: drafts[item.id]?.actual_qty !== undefined && drafts[item.id]?.actual_qty !== "" ? Number(drafts[item.id].actual_qty) : item.actual_qty,
        note: drafts[item.id]?.note ?? item.note ?? undefined
      }))
      .filter((item) => item.actual_qty !== null) as Array<{ item_id: string; actual_qty: number; note?: string }>;

    if (!payload.length) {
      toast({ title: "ยังไม่มีรายการให้บันทึก", variant: "destructive" });
      return;
    }

    setSaving(true);
    try {
      await stockCountApi.batchUpdateItems(id, payload);
      toast({ title: `บันทึกแล้ว ${payload.length} รายการ` });
      await refreshSession();
    } catch (error) {
      toast({
        title: "บันทึกไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleDownloadSheet(): Promise<void> {
    if (!session) {
      return;
    }
    try {
      const response = await stockCountApi.downloadSheet(session.id);
      downloadBlob(response.data as Blob, `count_sheet_${session.session_number}.pdf`);
    } catch (error) {
      toast({
        title: "ดาวน์โหลดใบนับไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function handleDownloadVariance(): Promise<void> {
    if (!session) {
      return;
    }
    try {
      const response = await stockCountApi.downloadVariancePdf(session.id);
      downloadBlob(response.data as Blob, `variance_report_${session.session_number}.pdf`);
    } catch (error) {
      toast({
        title: "ดาวน์โหลดรายงานไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  function handleScanSubmit(): void {
    if (!scanValue.trim() || !session) {
      return;
    }
    const match = session.items.find((item) => item.sku.toLowerCase() === scanValue.trim().toLowerCase());
    if (!match) {
      toast({ title: `ไม่พบสินค้า: ${scanValue}`, variant: "destructive" });
      setScanValue("");
      return;
    }
    rowRefs.current[match.id]?.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightedId(match.id);
    setTimeout(() => setHighlightedId(null), 2000);
    const input = document.getElementById(`qty-input-${match.id}`) as HTMLInputElement | null;
    input?.focus();
    setScanValue("");
  }

  if (!session) {
    return <div className="py-10 text-center text-sm text-gray-500">กำลังโหลด session...</div>;
  }

  return (
    <div>
      <PageHeader
        title={`นับสินค้า ${session.session_number}`}
        subtitle="Stock Count Session"
        actions={
          <div className="flex flex-wrap gap-2">
            {session.status === "draft" ? <Button onClick={() => void handleStart()}>เริ่มนับ</Button> : null}
            {session.status === "in_progress" ? (
              <Button onClick={() => setCompleteOpen(true)}>
                <FileText className="h-4 w-4" />
                บันทึกและปิด session
              </Button>
            ) : null}
            {session.status === "completed" ? (
              <>
                <Button variant="outline" onClick={() => setReportOpen(true)}>
                  ดูรายงาน
                </Button>
                <Button variant="outline" onClick={() => void handleDownloadVariance()}>
                  <Download className="h-4 w-4" />
                  ดาวน์โหลด PDF
                </Button>
              </>
            ) : null}
          </div>
        }
      />

      <Card>
        <CardContent className="space-y-5 p-5">
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant={statusVariant(session.status)}>{session.status}</Badge>
            <span className="text-sm text-gray-600">สาขา: {branchMap.get(session.branch_id) ?? session.branch_id}</span>
            <span className="text-sm text-gray-600">คลัง: {locationMap.get(session.location_id) ?? session.location_id}</span>
            <span className="text-sm text-gray-600">วันที่นับ: {formatThaiDate(`${session.count_date}T00:00:00`)}</span>
          </div>

          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span>นับแล้ว {overallCounted} / {session.total_items} รายการ</span>
              <span>{completionPercent}%</span>
            </div>
            <div className="h-3 rounded-full bg-blue-100">
              <div className="h-3 rounded-full bg-blue-600 transition-all" style={{ width: `${completionPercent}%` }} />
            </div>
          </div>

          {session.status === "in_progress" ? (
            <div className="rounded-lg border border-gray-200 p-4">
              <label className="mb-2 block text-sm font-medium text-gray-700">สแกนบาร์โค้ดหรือพิมพ์ SKU</label>
              <div className="relative">
                <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                <Input
                  ref={scanInputRef}
                  className="h-12 pl-9 text-base"
                  value={scanValue}
                  onChange={(event) => setScanValue(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      handleScanSubmit();
                    }
                  }}
                  placeholder="สแกนบาร์โค้ดหรือพิมพ์ SKU"
                />
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {[
              { label: "ทั้งหมด", value: "all" },
              { label: "ยังไม่ได้นับ", value: "uncounted" },
              { label: "นับแล้ว", value: "counted" },
              { label: "มีผลต่าง", value: "variance" }
            ].map((pill) => (
              <Button
                key={pill.value}
                variant={filterMode === pill.value ? "default" : "outline"}
                size="sm"
                onClick={() => setFilterMode(pill.value as FilterMode)}
              >
                {pill.label}
              </Button>
            ))}
          </div>

          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-left">
                <tr>
                  <th className="px-3 py-3">#</th>
                  <th className="px-3 py-3">SKU</th>
                  <th className="px-3 py-3">ชื่อสินค้า</th>
                  <th className="px-3 py-3">หน่วย</th>
                  <th className="px-3 py-3 text-right">คาดไว้</th>
                  <th className="px-3 py-3 text-right">นับจริง</th>
                  <th className="px-3 py-3 text-right">ผลต่าง</th>
                  {session.status !== "in_progress" ? <th className="px-3 py-3 text-right">มูลค่าผลต่าง</th> : null}
                  <th className="px-3 py-3">หมายเหตุ</th>
                  <th className="px-3 py-3">สถานะ</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => {
                  const variance = Number(item.liveVarianceQty ?? 0);
                  const counted = item.liveActualQty !== null;
                  const rowClass = highlightedId === item.id
                    ? "bg-yellow-50"
                    : counted && variance !== 0
                      ? "bg-orange-50"
                      : counted
                        ? "bg-green-50"
                        : "";
                  return (
                    <tr key={item.id} ref={(node) => { rowRefs.current[item.id] = node; }} className={rowClass}>
                      <td className="px-3 py-3">{index + 1}</td>
                      <td className="px-3 py-3 font-mono text-xs">{item.sku}</td>
                      <td className="px-3 py-3 font-medium text-gray-900">{item.product_name}</td>
                      <td className="px-3 py-3">{item.unit_code ?? "-"}</td>
                      <td className="px-3 py-3 text-right text-gray-500">{item.expected_qty}</td>
                      <td className="px-3 py-3 text-right">
                        {session.status === "in_progress" ? (
                          <Input
                            id={`qty-input-${item.id}`}
                            type="number"
                            min="0"
                            value={drafts[item.id]?.actual_qty ?? ""}
                            onChange={(event) => setItemDraft(item.id, "actual_qty", event.target.value)}
                            className="ml-auto w-28 text-right"
                          />
                        ) : (
                          item.actual_qty ?? "-"
                        )}
                      </td>
                      <td className={`px-3 py-3 text-right ${
                        item.liveActualQty === null ? "text-gray-400" : variance === 0 ? "text-green-700" : variance < 0 ? "text-red-700" : "text-orange-700"
                      }`}>
                        {item.liveActualQty === null ? "-" : variance}
                      </td>
                      {session.status !== "in_progress" ? (
                        <td className="px-3 py-3 text-right">
                          {item.variance_value === null ? "-" : formatThaiCurrency(Math.abs(Number(item.variance_value)))}
                        </td>
                      ) : null}
                      <td className="px-3 py-3">
                        {session.status === "in_progress" ? (
                          <Input
                            value={drafts[item.id]?.note ?? ""}
                            onChange={(event) => setItemDraft(item.id, "note", event.target.value)}
                            placeholder="หมายเหตุ"
                          />
                        ) : (
                          item.note ?? "-"
                        )}
                      </td>
                      <td className="px-3 py-3">
                        {item.liveActualQty === null ? "○" : variance === 0 ? "✓ counted" : "⚠ variance"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {session.status === "in_progress" ? (
            <div className="sticky bottom-4 flex justify-end">
              <Button onClick={() => void handleSaveAll()} disabled={saving}>
                {saving ? "กำลังบันทึก..." : `บันทึกทั้งหมด (${overallCounted} รายการ)`}
              </Button>
            </div>
          ) : null}

          <div className="text-sm text-gray-500">กำลังแสดง {items.length} รายการ | นับแล้วในมุมมองนี้ {countedCount} รายการ</div>
        </CardContent>
      </Card>

      <CompleteDialog
        open={completeOpen}
        onOpenChange={setCompleteOpen}
        session={session}
        onCompleted={async () => {
          await refreshSession();
          navigate("/stock-count");
        }}
      />
      <VarianceReportDialog sessionId={id} open={reportOpen} onOpenChange={setReportOpen} />
    </div>
  );
}
