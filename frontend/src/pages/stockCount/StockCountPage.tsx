import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, Download, Eye, FileText, Play, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { authApi, systemApi } from "@/lib/api";
import { formatThaiCurrency, formatThaiDate } from "@/lib/cartUtils";
import { stockApi } from "@/lib/stockApi";
import { stockCountApi } from "@/lib/stockCountApi";
import { usePermission } from "@/hooks/usePermission";
import type { ApiResponse } from "@/types/api";
import type { StockLocation } from "@/types/stock";
import type { CountSessionListItem } from "@/types/stockCount";
import type { Branch, UserBranch } from "@/types/user";
import CreateSessionDialog from "@/pages/stockCount/CreateSessionDialog";
import VarianceReportDialog from "@/pages/stockCount/VarianceReportDialog";

const STATUS_BADGE: Record<string, "secondary" | "default" | "success" | "destructive"> = {
  draft: "secondary",
  in_progress: "default",
  completed: "success",
  cancelled: "destructive"
};

function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

export default function StockCountPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const canAdjust = usePermission("inventory.stock.adjust");
  const [branchId, setBranchId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [statusValue, setStatusValue] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [reportSessionId, setReportSessionId] = useState<string | null>(null);

  const branchesQuery = useQuery({
    queryKey: ["stock-count", "branches"],
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
    queryKey: ["stock-count", "locations"],
    queryFn: async () => {
      const response = await stockApi.listLocations();
      return response.data as ApiResponse<StockLocation[]>;
    }
  });

  const sessionsQuery = useQuery({
    queryKey: ["stock-count", "sessions", branchId, locationId, statusValue],
    queryFn: async () => {
      const response = await stockCountApi.listSessions({
        branch_id: branchId || undefined,
        location_id: locationId || undefined,
        status: statusValue || undefined,
        page: 1,
        limit: 100
      });
      return response.data as ApiResponse<CountSessionListItem[]>;
    }
  });

  const branches = branchesQuery.data?.data ?? [];
  const locations = useMemo(
    () => (locationsQuery.data?.data ?? []).filter((item) => !branchId || item.branch_id === branchId),
    [branchId, locationsQuery.data?.data]
  );
  const branchMap = useMemo(() => new Map(branches.map((item) => [item.id, item.name])), [branches]);
  const locationMap = useMemo(() => new Map((locationsQuery.data?.data ?? []).map((item) => [item.id, item.name])), [locationsQuery.data?.data]);
  const sessions = sessionsQuery.data?.data ?? [];

  async function refresh(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["stock-count", "sessions"] });
  }

  async function handleStart(id: string): Promise<void> {
    try {
      await stockCountApi.startSession(id);
      toast({ title: "เริ่มนับสินค้าแล้ว" });
      await refresh();
      navigate(`/stock-count/${id}`);
    } catch (error) {
      toast({
        title: "เริ่มนับไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function handleCancel(id: string): Promise<void> {
    try {
      await stockCountApi.cancelSession(id);
      toast({ title: "ยกเลิก session แล้ว" });
      await refresh();
    } catch (error) {
      toast({
        title: "ยกเลิกไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function handleDownloadSheet(id: string, sessionNumber: string): Promise<void> {
    try {
      const response = await stockCountApi.downloadSheet(id);
      downloadBlob(response.data as Blob, `count_sheet_${sessionNumber}.pdf`);
    } catch (error) {
      toast({
        title: "ดาวน์โหลดใบนับไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function handleDownloadVariance(id: string, sessionNumber: string): Promise<void> {
    try {
      const response = await stockCountApi.downloadVariancePdf(id);
      downloadBlob(response.data as Blob, `variance_report_${sessionNumber}.pdf`);
    } catch (error) {
      toast({
        title: "ดาวน์โหลดรายงานไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <div>
      <PageHeader
        title="นับสินค้า"
        subtitle="Stock Count Sessions"
        actions={
          canAdjust ? (
            <Button onClick={() => setCreateOpen(true)}>
              <ClipboardCheck className="h-4 w-4" />
              เริ่มนับสินค้า
            </Button>
          ) : null
        }
      />

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="grid gap-3 md:grid-cols-3">
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={branchId} onChange={(event) => setBranchId(event.target.value)}>
              <option value="">ทุกสาขา</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.name}
                </option>
              ))}
            </select>

            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={locationId} onChange={(event) => setLocationId(event.target.value)}>
              <option value="">ทุกคลัง</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>
                  {location.name}
                </option>
              ))}
            </select>

            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={statusValue} onChange={(event) => setStatusValue(event.target.value)}>
              <option value="">ทุกสถานะ</option>
              <option value="draft">draft</option>
              <option value="in_progress">in_progress</option>
              <option value="completed">completed</option>
              <option value="cancelled">cancelled</option>
            </select>
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>เลขที่</TableHead>
                  <TableHead>สาขา + คลัง</TableHead>
                  <TableHead>วันที่นับ</TableHead>
                  <TableHead>รายการทั้งหมด</TableHead>
                  <TableHead>ตรง / เกิน / ขาด</TableHead>
                  <TableHead>มูลค่าผลต่าง</TableHead>
                  <TableHead>สถานะ</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessions.map((session) => (
                  <TableRow key={session.id}>
                    <TableCell className="font-mono">{session.session_number}</TableCell>
                    <TableCell>
                      <p className="font-medium text-gray-900">{branchMap.get(session.branch_id) ?? session.branch_id}</p>
                      <p className="text-xs text-gray-500">{locationMap.get(session.location_id) ?? session.location_id}</p>
                    </TableCell>
                    <TableCell>{formatThaiDate(`${session.count_date}T00:00:00`)}</TableCell>
                    <TableCell>{session.total_items}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Badge variant="success">ตรง {session.items_matched}</Badge>
                        <Badge variant="default">เกิน {session.items_over}</Badge>
                        <Badge variant="destructive">ขาด {session.items_short}</Badge>
                      </div>
                    </TableCell>
                    <TableCell className={Number(session.total_variance_value) > 0 ? "text-red-600" : ""}>
                      {formatThaiCurrency(Number(session.total_variance_value))}
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_BADGE[session.status] ?? "secondary"}>{session.status}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        {session.status === "draft" ? (
                          <>
                            <Button size="sm" variant="outline" onClick={() => void handleStart(session.id)}>
                              <Play className="h-4 w-4" />
                              เริ่มนับ
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => void handleDownloadSheet(session.id, session.session_number)}>
                              <Download className="h-4 w-4" />
                              ดาวน์โหลดใบนับ
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => void handleCancel(session.id)}>
                              <XCircle className="h-4 w-4" />
                              ยกเลิก
                            </Button>
                          </>
                        ) : null}

                        {session.status === "in_progress" ? (
                          <>
                            <Button size="sm" variant="outline" onClick={() => navigate(`/stock-count/${session.id}`)}>
                              <FileText className="h-4 w-4" />
                              บันทึกผลการนับ
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => void handleDownloadSheet(session.id, session.session_number)}>
                              <Download className="h-4 w-4" />
                              ดาวน์โหลดใบนับ
                            </Button>
                          </>
                        ) : null}

                        {session.status === "completed" ? (
                          <>
                            <Button size="sm" variant="outline" onClick={() => setReportSessionId(session.id)}>
                              <Eye className="h-4 w-4" />
                              ดูรายงานผลต่าง
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => void handleDownloadVariance(session.id, session.session_number)}>
                              <Download className="h-4 w-4" />
                              ดาวน์โหลด PDF
                            </Button>
                          </>
                        ) : null}

                        {session.status === "cancelled" ? (
                          <Button size="sm" variant="outline" onClick={() => navigate(`/stock-count/${session.id}`)}>
                            ดูรายละเอียด
                          </Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <CreateSessionDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={refresh} />
      <VarianceReportDialog open={Boolean(reportSessionId)} onOpenChange={(open) => !open && setReportSessionId(null)} sessionId={reportSessionId} />
    </div>
  );
}
