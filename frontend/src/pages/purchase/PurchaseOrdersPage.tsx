import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileDown, ReceiptText } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { authApi, systemApi } from "@/lib/api";
import { formatThaiCurrency, formatThaiDate } from "@/lib/cartUtils";
import { poApi, supplierApi } from "@/lib/purchaseApi";
import type { ApiResponse } from "@/types/api";
import type { POListItem, Supplier } from "@/types/purchase";
import type { Branch, UserBranch } from "@/types/user";
import { usePermission } from "@/hooks/usePermission";

const STATUS_LABELS: Record<string, string> = {
  draft: "draft",
  pending_approval: "pending_approval",
  approved: "approved",
  partially_received: "partially_received",
  fully_received: "fully_received",
  cancelled: "cancelled"
};

const STATUS_CLASSES: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  pending_approval: "bg-yellow-100 text-yellow-800",
  approved: "bg-blue-100 text-blue-700",
  partially_received: "bg-orange-100 text-orange-700",
  fully_received: "bg-green-100 text-green-700",
  cancelled: "bg-red-100 text-red-700"
};

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function PurchaseOrdersPage(): JSX.Element {
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const canCreate = usePermission("inventory.purchase.create");
  const canApprove = usePermission("inventory.purchase.approve");
  const [supplierId, setSupplierId] = useState("");
  const [statusValue, setStatusValue] = useState("");
  const [branchId, setBranchId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const suppliersQuery = useQuery({
    queryKey: ["purchase", "suppliers", "filters"],
    queryFn: async () => {
      const response = await supplierApi.list({ page: 1, limit: 100 });
      return response.data as ApiResponse<Supplier[]>;
    }
  });

  const branchesQuery = useQuery({
    queryKey: ["purchase", "branches"],
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

  const ordersQuery = useQuery({
    queryKey: ["purchase", "orders", supplierId, statusValue, branchId, dateFrom, dateTo],
    queryFn: async () => {
      const response = await poApi.list({
        supplier_id: supplierId || undefined,
        status: statusValue || undefined,
        branch_id: branchId || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page: 1,
        limit: 100
      });
      return response.data as ApiResponse<POListItem[]>;
    }
  });

  const rows = useMemo(() => ordersQuery.data?.data ?? [], [ordersQuery.data?.data]);

  async function handleApprove(orderId: string): Promise<void> {
    try {
      await poApi.approve(orderId, "อนุมัติจากหน้ารายการ");
      toast({ title: "อนุมัติ PO แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["purchase", "orders"] });
    } catch (error) {
      toast({
        title: "อนุมัติไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  async function handleDownloadPdf(orderId: string, poNumber: string): Promise<void> {
    try {
      const response = await poApi.pdf(orderId);
      const contentType = String(response.headers["content-type"] ?? "");
      const isPdf = contentType.includes("pdf");
      downloadBlob(response.data as Blob, `${poNumber}.${isPdf ? "pdf" : "html"}`);
    } catch (error) {
      toast({
        title: "ดาวน์โหลดไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <div>
      <PageHeader
        title="ใบสั่งซื้อ"
        subtitle="Purchase Orders"
        actions={
          canCreate ? (
            <Button onClick={() => navigate("/purchase/orders/new")}>
              สร้าง PO
            </Button>
          ) : null
        }
      />

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <select
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              value={supplierId}
              onChange={(event) => setSupplierId(event.target.value)}
            >
              <option value="">ทุกผู้จำหน่าย</option>
              {(suppliersQuery.data?.data ?? []).map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
            </select>
            <select
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              value={statusValue}
              onChange={(event) => setStatusValue(event.target.value)}
            >
              <option value="">ทุกสถานะ</option>
              {Object.keys(STATUS_LABELS).map((statusKey) => (
                <option key={statusKey} value={statusKey}>{STATUS_LABELS[statusKey]}</option>
              ))}
            </select>
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
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>เลขที่ PO</TableHead>
                  <TableHead>วันที่สั่ง</TableHead>
                  <TableHead>ต้องการวันที่</TableHead>
                  <TableHead>ผู้จำหน่าย</TableHead>
                  <TableHead>จำนวนรายการ</TableHead>
                  <TableHead className="text-right">ยอดรวม</TableHead>
                  <TableHead className="text-right">ยังค้างชำระ</TableHead>
                  <TableHead>สถานะ</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((order) => (
                  <TableRow key={order.id}>
                    <TableCell className="font-mono">
                      <Link className="text-blue-600 hover:underline" to={`/purchase/orders/${order.id}`}>
                        {order.po_number}
                      </Link>
                    </TableCell>
                    <TableCell>{formatThaiDate(`${order.order_date}T00:00:00`)}</TableCell>
                    <TableCell>{order.expected_date ? formatThaiDate(`${order.expected_date}T00:00:00`) : "ไม่ระบุ"}</TableCell>
                    <TableCell>{order.supplier_name}</TableCell>
                    <TableCell>{order.item_count}</TableCell>
                    <TableCell className="text-right">{formatThaiCurrency(Number(order.total_amount))}</TableCell>
                    <TableCell className={`text-right ${Number(order.remaining_amount) > 0 ? "text-red-600" : ""}`}>
                      {formatThaiCurrency(Number(order.remaining_amount))}
                    </TableCell>
                    <TableCell>
                      <Badge className={STATUS_CLASSES[order.status] ?? ""} variant="secondary">
                        {STATUS_LABELS[order.status] ?? order.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Button variant="outline" size="sm" onClick={() => navigate(`/purchase/orders/${order.id}`)}>
                          ดู/แก้ไข
                        </Button>
                        {order.status === "pending_approval" && canApprove ? (
                          <Button variant="outline" size="sm" onClick={() => void handleApprove(order.id)}>
                            <CheckCircle2 className="h-4 w-4" />
                            อนุมัติ
                          </Button>
                        ) : null}
                        {(order.status === "approved" || order.status === "partially_received") ? (
                          <Button variant="outline" size="sm" onClick={() => navigate(`/purchase/orders/${order.id}`)}>
                            <ReceiptText className="h-4 w-4" />
                            รับสินค้า
                          </Button>
                        ) : null}
                        <Button variant="outline" size="sm" onClick={() => void handleDownloadPdf(order.id, order.po_number)}>
                          <FileDown className="h-4 w-4" />
                          PDF
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
