import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { hrApi } from "@/lib/hrApi";
import type { PayrollRun } from "@/types/hr";

type Props = {
  runId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value || 0);
}

function statusBadge(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "completed") {
    return "default";
  }
  if (status === "cancelled") {
    return "destructive";
  }
  if (status === "draft") {
    return "secondary";
  }
  return "outline";
}

export default function PayrollRunDetailDialog({ runId, open, onOpenChange }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const runQuery = useQuery({
    queryKey: ["hr", "payroll-run", runId],
    enabled: open && Boolean(runId),
    queryFn: async () => (await hrApi.getPayrollRun(runId ?? "")).data.data
  });

  const processMutation = useMutation({
    mutationFn: async () => hrApi.processPayroll(runId ?? ""),
    onSuccess: async () => {
      toast({ title: "ประมวลผลเงินเดือนแล้ว" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["hr"] }),
        queryClient.invalidateQueries({ queryKey: ["hr", "payroll-run", runId] })
      ]);
    },
    onError: (error: Error) => {
      toast({ title: "ประมวลผลไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const run = runQuery.data as PayrollRun | undefined;

  async function downloadPayslip(employeeId: string, employeeCode: string): Promise<void> {
    if (!runId) {
      return;
    }
    const response = await hrApi.downloadPayslip(runId, employeeId);
    const blob = new Blob([response.data], { type: String(response.headers["content-type"] || "application/pdf") });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `payslip_${employeeCode}_${run?.run_number ?? "run"}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-6xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <span>{run?.run_number ?? "รอบเงินเดือน"}</span>
            {run ? <Badge variant={statusBadge(run.status)}>{run.status}</Badge> : null}
          </DialogTitle>
        </DialogHeader>

        {run?.status === "draft" ? (
          <Card className="border-emerald-200 bg-emerald-50">
            <CardContent className="flex flex-col gap-3 p-5 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="font-semibold text-emerald-900">เมื่อประมวลผลแล้วจะคำนวณ SSO และ PIT อัตโนมัติ</p>
                <p className="text-sm text-emerald-700">ตรวจสอบงวดและวันจ่ายก่อนยืนยัน</p>
              </div>
              <Button className="bg-emerald-600 hover:bg-emerald-700" onClick={() => processMutation.mutate()} disabled={processMutation.isPending}>
                {processMutation.isPending ? "กำลังประมวลผล..." : "ประมวลผลเงินเดือน"}
              </Button>
            </CardContent>
          </Card>
        ) : null}

        {run?.status === "completed" ? (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-4">
              <SummaryCard label="พนักงาน" value={String(run.total_employees)} />
              <SummaryCard label="รายได้รวม" value={formatCurrency(run.total_gross)} />
              <SummaryCard label="รายการหัก" value={formatCurrency(run.total_deductions)} />
              <SummaryCard label="สุทธิจ่าย" value={formatCurrency(run.total_net)} accent />
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <SummaryCard label="SSO พนักงาน" value={formatCurrency(run.total_sso_employee)} />
              <SummaryCard label="SSO นายจ้าง" value={formatCurrency(run.total_sso_employer)} />
              <SummaryCard label="PIT รวม" value={formatCurrency(run.total_pit)} />
            </div>

            <div className="overflow-x-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>รหัส</TableHead>
                    <TableHead>ชื่อ</TableHead>
                    <TableHead>แผนก</TableHead>
                    <TableHead>รายได้</TableHead>
                    <TableHead>SSO</TableHead>
                    <TableHead>PIT</TableHead>
                    <TableHead>สุทธิ</TableHead>
                    <TableHead>สลิป PDF</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(run.items ?? []).map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono">{item.employee_code}</TableCell>
                      <TableCell>{item.employee_name}</TableCell>
                      <TableCell>{item.department_name ?? "-"}</TableCell>
                      <TableCell>{formatCurrency(item.earnings_total)}</TableCell>
                      <TableCell>{formatCurrency(item.sso_employee)}</TableCell>
                      <TableCell>{formatCurrency(item.pit_withheld)}</TableCell>
                      <TableCell className="font-semibold text-blue-700">{formatCurrency(item.net_pay)}</TableCell>
                      <TableCell>
                        <Button variant="outline" size="sm" onClick={() => void downloadPayslip(item.employee_id, item.employee_code)}>
                          <Download className="h-4 w-4" />
                          ดาวน์โหลด
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function SummaryCard({ label, value, accent = false }: { label: string; value: string; accent?: boolean }): JSX.Element {
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <p className="text-sm text-gray-500">{label}</p>
        <p className={accent ? "text-2xl font-bold text-blue-700" : "text-2xl font-semibold text-gray-900"}>{value}</p>
      </CardContent>
    </Card>
  );
}
