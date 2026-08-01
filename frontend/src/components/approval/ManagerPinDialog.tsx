import { useQuery } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
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
import { approvalApi, errorMessage } from "@/lib/approvalApi";

type ManagerPinDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export default function ManagerPinDialog({ open, onOpenChange }: ManagerPinDialogProps): JSX.Element {
  const { toast } = useToast();
  const [currentPassword, setCurrentPassword] = useState("");
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const statusQuery = useQuery({
    queryKey: ["approvals", "manager-pin"],
    queryFn: async () => (await approvalApi.getManagerPinStatus()).data.data,
    enabled: open
  });

  useEffect(() => {
    if (open) {
      setCurrentPassword("");
      setPin("");
      setConfirmPin("");
    }
  }, [open]);

  async function submit(): Promise<void> {
    if (pin !== confirmPin) {
      toast({ title: "PIN ทั้งสองช่องไม่ตรงกัน", variant: "destructive" });
      return;
    }
    setIsSubmitting(true);
    try {
      await approvalApi.setManagerPin({ current_password: currentPassword, pin });
      await statusQuery.refetch();
      toast({ title: statusQuery.data?.is_set ? "เปลี่ยน Manager PIN แล้ว" : "ตั้ง Manager PIN แล้ว" });
      onOpenChange(false);
    } catch (error) {
      toast({
        title: "ตั้ง Manager PIN ไม่สำเร็จ",
        description: errorMessage(error, "ตรวจสอบรหัสผ่านและรูปแบบ PIN"),
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
            <KeyRound className="h-5 w-5 text-blue-600" />
            {statusQuery.data?.is_set ? "เปลี่ยน Manager PIN" : "ตั้ง Manager PIN"}
          </DialogTitle>
          <DialogDescription>
            ใช้ PIN เฉพาะการอนุมัติรายการที่เกินสิทธิ์พนักงาน ไม่ใช้แทนรหัสผ่านเข้าสู่ระบบ
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="manager-current-password">รหัสผ่านปัจจุบัน</Label>
            <Input
              id="manager-current-password"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="manager-new-pin">PIN ใหม่ 6 หลัก</Label>
              <Input
                id="manager-new-pin"
                type="password"
                inputMode="numeric"
                maxLength={6}
                value={pin}
                onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="manager-confirm-pin">ยืนยัน PIN</Label>
              <Input
                id="manager-confirm-pin"
                type="password"
                inputMode="numeric"
                maxLength={6}
                value={confirmPin}
                onChange={(event) => setConfirmPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
              />
            </div>
          </div>
          <p className="text-xs text-gray-500">
            ห้ามใช้เลขซ้ำทั้งชุด, 123456 หรือ 654321; กรอกผิดครบ 5 ครั้งจะถูกล็อก 15 นาที
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            ยกเลิก
          </Button>
          <Button
            onClick={() => void submit()}
            disabled={isSubmitting || !currentPassword || pin.length !== 6 || confirmPin.length !== 6}
          >
            {isSubmitting ? "กำลังบันทึก..." : "บันทึก PIN"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
