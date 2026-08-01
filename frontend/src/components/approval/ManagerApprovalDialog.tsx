import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { approvalApi, compactApprovalPayload, errorMessage } from "@/lib/approvalApi";
import type { ApprovalAction } from "@/types/approval";

type ManagerApprovalDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  action: ApprovalAction;
  requestPayload: Record<string, unknown>;
  reason: string;
  description: string;
  onApproved: (approvalToken: string) => Promise<void>;
};

export default function ManagerApprovalDialog({
  open,
  onOpenChange,
  action,
  requestPayload,
  reason,
  description,
  onApproved
}: ManagerApprovalDialogProps): JSX.Element {
  const { toast } = useToast();
  const [approverUsername, setApproverUsername] = useState("");
  const [managerPin, setManagerPin] = useState("");
  const [approvalReason, setApprovalReason] = useState(reason);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setManagerPin("");
      setApprovalReason(reason);
    }
  }, [open, reason]);

  async function submit(): Promise<void> {
    if (!approverUsername.trim() || managerPin.length !== 6 || approvalReason.trim().length < 3) {
      toast({
        title: "ข้อมูลอนุมัติยังไม่ครบ",
        description: "กรอก username ผู้อนุมัติ, PIN 6 หลัก และเหตุผลอย่างน้อย 3 ตัวอักษร",
        variant: "destructive"
      });
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await approvalApi.createSession({
        approver_username: approverUsername.trim(),
        manager_pin: managerPin,
        action,
        reason: approvalReason.trim(),
        request_payload: compactApprovalPayload(requestPayload)
      });
      await onApproved(response.data.data.approval_token);
      toast({
        title: "Manager อนุมัติแล้ว",
        description: `อนุมัติโดย ${response.data.data.approver_display_name}`
      });
      onOpenChange(false);
      setManagerPin("");
    } catch (error) {
      toast({
        title: "อนุมัติรายการไม่สำเร็จ",
        description: errorMessage(error, "ตรวจสอบสิทธิ์ Manager และลองอีกครั้ง"),
        variant: "destructive"
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !isSubmitting && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-blue-600" />
            ขออนุมัติจาก Manager
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="approval-manager-username">Username ผู้อนุมัติ</Label>
            <Input
              id="approval-manager-username"
              autoComplete="username"
              value={approverUsername}
              onChange={(event) => setApproverUsername(event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="approval-manager-pin">Manager PIN</Label>
            <Input
              id="approval-manager-pin"
              type="password"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={managerPin}
              onChange={(event) => setManagerPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
              onKeyDown={(event) => {
                if (event.key === "Enter") void submit();
              }}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="approval-reason">เหตุผลอนุมัติ</Label>
            <textarea
              id="approval-reason"
              className="min-h-[88px] rounded-md border border-gray-300 px-3 py-2 text-sm"
              maxLength={500}
              value={approvalReason}
              onChange={(event) => setApprovalReason(event.target.value)}
            />
          </div>
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
            PIN ไม่ถูกส่งต่อไปยังรายการขายและ approval ใช้ได้ครั้งเดียวภายใน 2 นาที
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            ยกเลิก
          </Button>
          <Button onClick={() => void submit()} disabled={isSubmitting}>
            {isSubmitting ? "กำลังตรวจสอบ..." : "อนุมัติและทำรายการ"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
