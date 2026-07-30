import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { hrApi } from "@/lib/hrApi";
import type { EmployeeListItem } from "@/types/hr";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employees: EmployeeListItem[];
};

function toDateTime(dateValue: string, timeValue: string): string | null {
  if (!dateValue || !timeValue) return null;
  return `${dateValue}T${timeValue}:00+07:00`;
}

function formatMinutes(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours} ชม. ${mins} นาที`;
}

export default function RecordAttendanceDialog({ open, onOpenChange, employees }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [workDate, setWorkDate] = useState(new Date().toISOString().slice(0, 10));
  const [clockIn, setClockIn] = useState("");
  const [clockOut, setClockOut] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!open) {
      setSearch("");
      setEmployeeId("");
      setWorkDate(new Date().toISOString().slice(0, 10));
      setClockIn("");
      setClockOut("");
      setNote("");
    }
  }, [open]);

  const filteredEmployees = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return employees.filter((employee) => {
      if (!keyword) return true;
      return [
        employee.employee_code,
        employee.first_name,
        employee.last_name,
        [employee.first_name, employee.last_name].join(" ")
      ].some((value) => value.toLowerCase().includes(keyword));
    });
  }, [employees, search]);

  const preview = useMemo(() => {
    if (!workDate || !clockIn || !clockOut) return null;
    const start = new Date(`${workDate}T${clockIn}:00+07:00`);
    const end = new Date(`${workDate}T${clockOut}:00+07:00`);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) return null;
    const totalMinutes = Math.max(Math.round((end.getTime() - start.getTime()) / 60000) - 60, 0);
    const otMinutes = Math.max(Math.round((end.getTime() - new Date(`${workDate}T17:00:00+07:00`).getTime()) / 60000), 0);
    const lateMinutes = Math.max(Math.round((start.getTime() - new Date(`${workDate}T08:00:00+07:00`).getTime()) / 60000), 0);
    const otAmount = ((otMinutes / 60) * ((25000 / 26 / 8) * 1.5)).toFixed(2);
    return { totalMinutes, otMinutes, lateMinutes, otAmount };
  }, [workDate, clockIn, clockOut]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!employeeId || !workDate) {
        throw new Error("กรุณาเลือกพนักงานและวันที่");
      }
      return hrApi.recordAttendance({
        employee_id: employeeId,
        work_date: workDate,
        clock_in: toDateTime(workDate, clockIn),
        clock_out: toDateTime(workDate, clockOut),
        note: note || null
      });
    },
    onSuccess: async () => {
      toast({ title: "บันทึกการเข้างานแล้ว" });
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["hr"] });
    },
    onError: (error: Error) => {
      toast({ title: "บันทึกไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>บันทึกย้อนหลัง</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="space-y-2">
            <Label>ค้นหาพนักงาน</Label>
            <Input placeholder="ค้นหารหัสหรือชื่อ" value={search} onChange={(event) => setSearch(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>พนักงาน *</Label>
            <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}>
              <option value="">เลือกพนักงาน</option>
              {filteredEmployees.map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.employee_code} • {[employee.first_name, employee.last_name].join(" ")}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>วันที่ *</Label>
              <Input type="date" value={workDate} onChange={(event) => setWorkDate(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>หมายเหตุ</Label>
              <Input value={note} onChange={(event) => setNote(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>เวลาเข้า</Label>
              <Input type="time" value={clockIn} onChange={(event) => setClockIn(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>เวลาออก</Label>
              <Input type="time" value={clockOut} onChange={(event) => setClockOut(event.target.value)} />
            </div>
          </div>
          {preview ? (
            <div className="rounded-lg border bg-slate-50 p-3 text-sm">
              <div>ชั่วโมงทำงาน: {formatMinutes(preview.totalMinutes)}</div>
              <div>OT: {preview.otMinutes} นาที (฿ {preview.otAmount})</div>
              <div>สถานะ: {preview.lateMinutes > 5 ? `สาย ${preview.lateMinutes} นาที` : "ปกติ"}</div>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? "กำลังบันทึก..." : "บันทึก"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
