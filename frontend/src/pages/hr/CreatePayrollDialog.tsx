import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { hrApi } from "@/lib/hrApi";
import type { BranchDetail } from "@/types/admin";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  branches: BranchDetail[];
  onCreated: (runId: string) => Promise<void> | void;
};

function getLastDayOfMonth(year: number, month: number): string {
  return new Date(year, month, 0).toISOString().slice(0, 10);
}

export default function CreatePayrollDialog({ open, onOpenChange, branches, onCreated }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const now = new Date();
  const [periodYear, setPeriodYear] = useState(String(now.getFullYear()));
  const [periodMonth, setPeriodMonth] = useState(String(now.getMonth() + 1));
  const [payDate, setPayDate] = useState(getLastDayOfMonth(now.getFullYear(), now.getMonth() + 1));
  const [branchId, setBranchId] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!open) {
      return;
    }
    const year = Number(periodYear || now.getFullYear());
    const month = Number(periodMonth || now.getMonth() + 1);
    setPayDate(getLastDayOfMonth(year, month));
  }, [open, periodYear, periodMonth, now]);

  const createMutation = useMutation({
    mutationFn: async () =>
      hrApi.createPayrollRun({
        period_year: Number(periodYear),
        period_month: Number(periodMonth),
        pay_date: payDate,
        branch_id: branchId || null,
        note: note || null
      }),
    onSuccess: async (response) => {
      toast({ title: "สร้างรอบเงินเดือนแล้ว" });
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["hr"] });
      await Promise.resolve(onCreated(response.data.data.id));
    },
    onError: (error: Error) => {
      toast({ title: "สร้างรอบเงินเดือนไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>สร้างรอบเงินเดือน</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>ปี (ค.ศ.)</Label>
            <Input type="number" value={periodYear} onChange={(event) => setPeriodYear(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>เดือน</Label>
            <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={periodMonth} onChange={(event) => setPeriodMonth(event.target.value)}>
              {Array.from({ length: 12 }, (_, index) => (
                <option key={index + 1} value={index + 1}>{index + 1}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>วันจ่ายเงินเดือน</Label>
            <Input type="date" value={payDate} onChange={(event) => setPayDate(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>สาขา</Label>
            <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={branchId} onChange={(event) => setBranchId(event.target.value)}>
              <option value="">ทุกสาขา</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>{branch.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>หมายเหตุ</Label>
            <textarea className="min-h-[100px] w-full rounded-md border border-gray-300 px-3 py-2" value={note} onChange={(event) => setNote(event.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
            {createMutation.isPending ? "กำลังสร้าง..." : "สร้างรอบเงินเดือน"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
