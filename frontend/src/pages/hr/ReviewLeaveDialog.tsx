import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { hrApi } from "@/lib/hrApi";
import type { LeaveRequest } from "@/types/hr";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  leaveRequest: LeaveRequest | null;
};

export default function ReviewLeaveDialog({ open, onOpenChange, leaveRequest }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [reviewNote, setReviewNote] = useState("");

  useEffect(() => {
    if (!open) {
      setReviewNote("");
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: async (action: "approve" | "reject") => {
      if (!leaveRequest) throw new Error("ไม่พบคำขอลา");
      return hrApi.reviewLeaveRequest(leaveRequest.id, { action, review_note: reviewNote || null });
    },
    onSuccess: async () => {
      toast({ title: "อัปเดตคำขอลาแล้ว" });
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["hr"] });
    },
    onError: (error: Error) => {
      toast({ title: "อัปเดตไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const cancelMutation = useMutation({
    mutationFn: async () => {
      if (!leaveRequest) throw new Error("ไม่พบคำขอลา");
      return hrApi.cancelLeaveRequest(leaveRequest.id);
    },
    onSuccess: async () => {
      toast({ title: "ยกเลิกคำขอลาแล้ว" });
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["hr"] });
    },
    onError: (error: Error) => {
      toast({ title: "ยกเลิกไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>ตรวจสอบคำขอลา</DialogTitle>
        </DialogHeader>
        {leaveRequest ? (
          <div className="space-y-4">
            <div className="grid gap-2 text-sm">
              <div>พนักงาน: {leaveRequest.employee_name}</div>
              <div>ประเภทลา: {leaveRequest.leave_type_name}</div>
              <div>ช่วงวันที่: {leaveRequest.start_date} - {leaveRequest.end_date}</div>
              <div>จำนวนวัน: {leaveRequest.days_requested}</div>
              <div>เหตุผล: {leaveRequest.reason || "-"}</div>
            </div>
            <div className="space-y-2">
              <Label>หมายเหตุผู้อนุมัติ</Label>
              <textarea className="min-h-[100px] w-full rounded-md border border-gray-300 px-3 py-2" value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} />
            </div>
          </div>
        ) : null}
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>ปิด</Button>
          {leaveRequest?.status === "pending" ? (
            <>
              <Button className="bg-green-600 hover:bg-green-700" onClick={() => mutation.mutate("approve")} disabled={mutation.isPending || cancelMutation.isPending}>อนุมัติ</Button>
              <Button variant="destructive" onClick={() => mutation.mutate("reject")} disabled={mutation.isPending || cancelMutation.isPending}>ปฏิเสธ</Button>
              <Button variant="secondary" onClick={() => cancelMutation.mutate()} disabled={mutation.isPending || cancelMutation.isPending}>ยกเลิก</Button>
            </>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
