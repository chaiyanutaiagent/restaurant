import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Pencil, Truck, Undo2 } from "lucide-react";
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
import { formatThaiDate } from "@/lib/cartUtils";
import { transferApi } from "@/lib/transferApi";
import type { ApiResponse } from "@/types/api";
import type { TOListItem } from "@/types/transfer";
import type { Branch, UserBranch } from "@/types/user";
import { usePermission } from "@/hooks/usePermission";

const STATUS_CLASSES: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  pending_approval: "bg-yellow-100 text-yellow-800",
  approved: "bg-blue-100 text-blue-700",
  in_transit: "bg-purple-100 text-purple-700",
  partially_received: "bg-orange-100 text-orange-700",
  completed: "bg-green-100 text-green-700",
  cancelled: "bg-red-100 text-red-700"
};

export default function TransferOrdersPage(): JSX.Element {
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const canCreate = usePermission("inventory.transfer.create");
  const canApprove = usePermission("inventory.transfer.approve");
  const [fromBranchId, setFromBranchId] = useState("");
  const [toBranchId, setToBranchId] = useState("");
  const [statusValue, setStatusValue] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const branchesQuery = useQuery({
    queryKey: ["transfer", "branches"],
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
    queryKey: ["transfer", "orders", fromBranchId, toBranchId, statusValue],
    queryFn: async () => {
      const response = await transferApi.list({
        from_branch_id: fromBranchId || undefined,
        to_branch_id: toBranchId || undefined,
        status: statusValue || undefined,
        page: 1,
        limit: 100
      });
      return response.data as ApiResponse<TOListItem[]>;
    }
  });

  const rows = useMemo(() => {
    return (ordersQuery.data?.data ?? []).filter((row) => {
      if (dateFrom && row.request_date < dateFrom) return false;
      if (dateTo && row.request_date > dateTo) return false;
      return true;
    });
  }, [dateFrom, dateTo, ordersQuery.data?.data]);

  async function submitOrder(id: string): Promise<void> {
    try {
      await transferApi.submit(id);
      toast({ title: "ส่งขออนุมัติแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer", "orders"] });
    } catch (error) {
      toast({ title: "ทำรายการไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  async function approveOrder(id: string): Promise<void> {
    try {
      const detail = await transferApi.get(id);
      const order = (detail.data as ApiResponse<import("@/types/transfer").TransferOrder>).data;
      await transferApi.approve(id, {
        items: order.items.map((item) => ({ item_id: item.id, qty_approved: item.qty_requested })),
        note: "อนุมัติครบตามขอ"
      });
      toast({ title: "อนุมัติ TO แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer", "orders"] });
    } catch (error) {
      toast({ title: "อนุมัติไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  async function shipOrder(id: string): Promise<void> {
    try {
      await transferApi.ship(id, "จัดส่งแล้ว");
      toast({ title: "บันทึกจัดส่งแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer", "orders"] });
    } catch (error) {
      toast({ title: "จัดส่งไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  async function receiveOrder(id: string): Promise<void> {
    try {
      const detail = await transferApi.get(id);
      const order = (detail.data as ApiResponse<import("@/types/transfer").TransferOrder>).data;
      await transferApi.receive(id, {
        items: order.items.map((item) => ({ item_id: item.id, qty_received: item.qty_sent ?? 0 }))
      });
      toast({ title: "ยืนยันรับสินค้าแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer", "orders"] });
    } catch (error) {
      toast({ title: "รับสินค้าไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  async function cancelOrder(id: string): Promise<void> {
    const reason = window.prompt("ระบุเหตุผลในการยกเลิก");
    if (!reason) return;
    try {
      await transferApi.cancel(id, reason);
      toast({ title: "ยกเลิก TO แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["transfer", "orders"] });
    } catch (error) {
      toast({ title: "ยกเลิกไม่สำเร็จ", description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง", variant: "destructive" });
    }
  }

  return (
    <div>
      <PageHeader
        title="โอนย้ายสินค้า"
        subtitle="Transfer Orders"
        actions={canCreate ? <Button onClick={() => navigate("/transfer/orders/new")}>สร้าง TO</Button> : null}
      />

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={fromBranchId} onChange={(e) => setFromBranchId(e.target.value)}>
              <option value="">จากทุกสาขา</option>
              {(branchesQuery.data?.data ?? []).map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name}</option>
              ))}
            </select>
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={toBranchId} onChange={(e) => setToBranchId(e.target.value)}>
              <option value="">ไปทุกสาขา</option>
              {(branchesQuery.data?.data ?? []).map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name}</option>
              ))}
            </select>
            <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={statusValue} onChange={(e) => setStatusValue(e.target.value)}>
              <option value="">ทุกสถานะ</option>
              {["draft", "pending_approval", "approved", "in_transit", "partially_received", "completed", "cancelled"].map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>เลขที่ TO</TableHead>
                  <TableHead>จาก → ไปยัง</TableHead>
                  <TableHead>วันที่ขอ</TableHead>
                  <TableHead>ต้องการวันที่</TableHead>
                  <TableHead>รายการ</TableHead>
                  <TableHead>ผู้ขอ</TableHead>
                  <TableHead>สถานะ</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="font-mono">
                      <Link className="text-blue-600 hover:underline" to={`/transfer/orders/${row.id}`}>{row.to_number}</Link>
                    </TableCell>
                    <TableCell>{row.from_branch_name} → {row.to_branch_name}</TableCell>
                    <TableCell>{formatThaiDate(`${row.request_date}T00:00:00`)}</TableCell>
                    <TableCell>{row.expected_date ? formatThaiDate(`${row.expected_date}T00:00:00`) : "ไม่ระบุ"}</TableCell>
                    <TableCell>{row.item_count}</TableCell>
                    <TableCell>{row.requested_by_name}</TableCell>
                    <TableCell><Badge variant="secondary" className={STATUS_CLASSES[row.status] ?? ""}>{row.status}</Badge></TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        {row.status === "draft" ? (
                          <>
                            <Button variant="outline" size="sm" onClick={() => navigate(`/transfer/orders/${row.id}`)}><Pencil className="h-4 w-4" />แก้ไข</Button>
                            <Button variant="outline" size="sm" onClick={() => void submitOrder(row.id)}>ส่งอนุมัติ</Button>
                          </>
                        ) : null}
                        {row.status === "pending_approval" ? (
                          <>
                            {canApprove ? <Button variant="outline" size="sm" onClick={() => void approveOrder(row.id)}><CheckCircle2 className="h-4 w-4" />อนุมัติ</Button> : null}
                            <Button variant="outline" size="sm" onClick={() => void cancelOrder(row.id)}><Undo2 className="h-4 w-4" />ยกเลิก</Button>
                          </>
                        ) : null}
                        {row.status === "approved" ? (
                          <>
                            <Button variant="outline" size="sm" onClick={() => void shipOrder(row.id)}><Truck className="h-4 w-4" />จัดส่ง</Button>
                            <Button variant="outline" size="sm" onClick={() => void cancelOrder(row.id)}>ยกเลิก</Button>
                          </>
                        ) : null}
                        {["in_transit", "partially_received"].includes(row.status) ? (
                          <Button variant="outline" size="sm" onClick={() => void receiveOrder(row.id)}>ยืนยันรับ</Button>
                        ) : null}
                        {["completed", "cancelled"].includes(row.status) ? (
                          <Button variant="outline" size="sm" onClick={() => navigate(`/transfer/orders/${row.id}`)}>ดูรายละเอียด</Button>
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
    </div>
  );
}
