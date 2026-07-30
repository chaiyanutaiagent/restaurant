import { useQuery } from "@tanstack/react-query";
import { Download, Eye } from "lucide-react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/use-toast";
import { authApi, systemApi } from "@/lib/api";
import { formatThaiCurrency, formatThaiDate } from "@/lib/cartUtils";
import { posApi } from "@/lib/posApi";
import { reportApi } from "@/lib/reportApi";
import type { ApiResponse } from "@/types/api";
import type { CashierShift } from "@/types/pos";
import type { ShiftSummary } from "@/types/report";
import type { Branch, UserBranch } from "@/types/user";
import ShiftSummaryDialog from "@/pages/reports/ShiftSummaryDialog";

type ShiftStatusFilter = "all" | "open" | "closed";

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function ShiftHistoryPage(): JSX.Element {
  const { toast } = useToast();
  const [branchId, setBranchId] = useState("");
  const [statusFilter, setStatusFilter] = useState<ShiftStatusFilter>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedShiftId, setSelectedShiftId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const branchesQuery = useQuery({
    queryKey: ["branches", "reports"],
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

  const shiftsQuery = useQuery({
    queryKey: ["pos", "shifts", "history", branchId],
    queryFn: async () => {
      const response = await posApi.listShifts({ branch_id: branchId || undefined, page: 1, limit: 200 });
      return response.data as ApiResponse<CashierShift[]>;
    }
  });

  const summaryQuery = useQuery({
    queryKey: ["reports", "shift-summary", selectedShiftId],
    queryFn: async () => {
      const response = await reportApi.shiftSummary(selectedShiftId as string);
      return response.data as ApiResponse<ShiftSummary>;
    },
    enabled: Boolean(selectedShiftId)
  });

  const rows = useMemo(() => {
    const shifts = shiftsQuery.data?.data ?? [];
    return shifts.filter((shift) => {
      if (statusFilter !== "all" && shift.status !== statusFilter) {
        return false;
      }
      const openedDate = shift.opened_at.slice(0, 10);
      if (dateFrom && openedDate < dateFrom) {
        return false;
      }
      if (dateTo && openedDate > dateTo) {
        return false;
      }
      return true;
    });
  }, [dateFrom, dateTo, shiftsQuery.data?.data, statusFilter]);

  async function handleOpenSummary(shiftId: string): Promise<void> {
    setSelectedShiftId(shiftId);
    setDialogOpen(true);
  }

  async function handleDownloadPdf(shiftId: string): Promise<void> {
    try {
      const response = await reportApi.shiftPdf(shiftId);
      const contentType = String(response.headers["content-type"] ?? "");
      const isPdf = contentType.includes("pdf");
      downloadBlob(response.data as Blob, isPdf ? `shift_${shiftId}.pdf` : `shift_${shiftId}.html`);
    } catch {
      toast({
        title: "ดาวน์โหลดไม่สำเร็จ",
        description: "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <div>
      <PageHeader title="ประวัติกะ" subtitle="สรุปการทำงานแต่ละกะ" />

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <select
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              value={branchId}
              onChange={(event) => setBranchId(event.target.value)}
            >
              <option value="">ทุกสาขา</option>
              {(branchesQuery.data?.data ?? []).map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.name}
                </option>
              ))}
            </select>
            <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            <select
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as ShiftStatusFilter)}
            >
              <option value="all">ทุกสถานะ</option>
              <option value="open">กำลังเปิด</option>
              <option value="closed">ปิดแล้ว</option>
            </select>
          </div>

          <div className="overflow-x-auto">
            {shiftsQuery.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : (
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="px-3 py-3">เลขกะ</th>
                    <th className="px-3 py-3">ช่วงเวลา</th>
                    <th className="px-3 py-3">ยอดขาย</th>
                    <th className="px-3 py-3">จำนวนบิล</th>
                    <th className="px-3 py-3">ยกเลิก</th>
                    <th className="px-3 py-3">เงินสดคาด/จริง/ส่วนต่าง</th>
                    <th className="px-3 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((shift) => {
                    const diff = Number(shift.cash_difference ?? 0);
                    return (
                      <tr key={shift.id} className="border-b align-top last:border-0">
                        <td className="px-3 py-3 font-mono">{shift.shift_number}</td>
                        <td className="px-3 py-3">
                          <div>{formatThaiDate(shift.opened_at)}</div>
                          <div className="text-xs text-gray-500">
                            {shift.closed_at ? formatThaiDate(shift.closed_at) : "ยังเปิดอยู่"}
                          </div>
                        </td>
                        <td className="px-3 py-3 font-medium">{formatThaiCurrency(Number(shift.total_sales))}</td>
                        <td className="px-3 py-3">{shift.total_orders}</td>
                        <td className="px-3 py-3">{shift.total_voids}</td>
                        <td className="px-3 py-3">
                          <div>{formatThaiCurrency(Number(shift.expected_cash ?? shift.opening_cash))}</div>
                          <div>{shift.closing_cash !== null ? formatThaiCurrency(Number(shift.closing_cash)) : "-"}</div>
                          <div className={diff === 0 ? "text-green-600" : "text-red-600"}>
                            {formatThaiCurrency(diff)}
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex gap-2">
                            <Button variant="outline" size="sm" onClick={() => void handleOpenSummary(shift.id)}>
                              <Eye className="h-4 w-4" />
                              ดูสรุป
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => void handleDownloadPdf(shift.id)}>
                              <Download className="h-4 w-4" />
                              พิมพ์
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </CardContent>
      </Card>

      <ShiftSummaryDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        summary={summaryQuery.data?.data ?? null}
        onDownloadPdf={async () => {
          if (selectedShiftId) {
            await handleDownloadPdf(selectedShiftId);
          }
        }}
      />
    </div>
  );
}
