import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { hrApi } from "@/lib/hrApi";
import type { EmployeeListItem, LeaveBalance, LeaveType } from "@/types/hr";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employees: EmployeeListItem[];
  leaveTypes: LeaveType[];
  year: number;
};

function countBusinessDays(startDate: string, endDate: string): number {
  if (!startDate || !endDate) return 0;
  const start = new Date(`${startDate}T00:00:00+07:00`);
  const end = new Date(`${endDate}T00:00:00+07:00`);
  if (end < start) return 0;
  let current = new Date(start);
  let count = 0;
  while (current <= end) {
    const day = current.getDay();
    if (day !== 0 && day !== 6) count += 1;
    current.setDate(current.getDate() + 1);
  }
  return count;
}

export default function CreateLeaveRequestDialog({ open, onOpenChange, employees, leaveTypes, year }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (!open) {
      setSearch("");
      setEmployeeId("");
      setLeaveTypeId("");
      setStartDate("");
      setEndDate("");
      setReason("");
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

  const balancesQuery = useQuery({
    queryKey: ["hr", "leave-balances", employeeId, year],
    queryFn: async () => {
      if (!employeeId) return [] as LeaveBalance[];
      return (await hrApi.listLeaveBalances(employeeId, year)).data.data;
    },
    enabled: open && Boolean(employeeId)
  });
  const currentBalances = balancesQuery.data ?? [];
  const currentDays = useMemo(() => countBusinessDays(startDate, endDate), [startDate, endDate]);
  const selectedBalance = currentBalances.find((balance) => balance.leave_type_id === leaveTypeId);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!employeeId || !leaveTypeId || !startDate || !endDate) {
        throw new Error("กรุณากรอกข้อมูลให้ครบ");
      }
      return hrApi.createLeaveRequest({
        employee_id: employeeId,
        leave_type_id: leaveTypeId,
        start_date: startDate,
        end_date: endDate,
        reason: reason || null
      });
    },
    onSuccess: async () => {
      toast({ title: "สร้างคำขอลาแล้ว" });
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["hr"] });
    },
    onError: (error: Error) => {
      toast({ title: "สร้างคำขอไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>ขอลา</DialogTitle>
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
          <div className="space-y-2">
            <Label>ประเภทลา *</Label>
            <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={leaveTypeId} onChange={(event) => setLeaveTypeId(event.target.value)}>
              <option value="">เลือกประเภทลา</option>
              {leaveTypes.map((leaveType) => {
                const balance = currentBalances.find((item) => item.leave_type_id === leaveType.id);
                return (
                  <option key={leaveType.id} value={leaveType.id}>
                    {leaveType.name} {balance ? `(คงเหลือ ${balance.remaining_days} วัน)` : ""}
                  </option>
                );
              })}
            </select>
            <p className="text-xs text-gray-500">คงเหลือ: {selectedBalance?.remaining_days ?? "-"} วัน</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>วันที่เริ่ม *</Label>
              <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>วันที่สิ้นสุด *</Label>
              <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
            </div>
          </div>
          <div className="rounded-lg border bg-slate-50 p-3 text-sm">
            <div>จำนวนวันลา: {currentDays} วัน (ไม่รวมวันหยุด)</div>
            {selectedBalance && currentDays > Number(selectedBalance.remaining_days) ? (
              <div className="text-red-600">วันลามากกว่าสิทธิ์คงเหลือ</div>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label>เหตุผล</Label>
            <textarea className="min-h-[100px] w-full rounded-md border border-gray-300 px-3 py-2" value={reason} onChange={(event) => setReason(event.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? "กำลังส่งคำขอ..." : "ส่งคำขอ"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
