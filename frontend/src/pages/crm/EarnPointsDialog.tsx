import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { crmApi } from "@/lib/crmApi";
import type { Customer, LoyaltySettings } from "@/types/crm";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customer: Customer | null;
  settings: LoyaltySettings | null;
};

export default function EarnPointsDialog({ open, onOpenChange, customer, settings }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("0");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!open) {
      setAmount("0");
      setNote("");
    }
  }, [open]);

  const previewPoints = useMemo(() => {
    if (!customer || !settings) return 0;
    const multiplier = customer.tier?.points_multiplier ?? 1;
    return Math.floor(Number(amount || 0) * settings.earn_rate * multiplier);
  }, [amount, customer, settings]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!customer) throw new Error("ไม่พบสมาชิก");
      return crmApi.earnPoints({
        customer_id: customer.id,
        sale_order_id: `manual-${Date.now()}`,
        spend_amount: Number(amount || 0),
        note: note || null
      });
    },
    onSuccess: async () => {
      toast({ title: `ได้รับ +${previewPoints} แต้ม` });
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["crm"] });
    },
    onError: (error: Error) => {
      toast({ title: "ให้แต้มไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>ให้แต้ม</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="rounded-lg border bg-slate-50 p-3 text-sm">
            <div>{customer?.display_name || customer?.first_name || "-"}</div>
            <div>แต้มปัจจุบัน: {customer?.points_balance ?? 0} ⭐</div>
          </div>
          <div className="space-y-2">
            <Label>ยอดซื้อ (฿)</Label>
            <Input type="number" value={amount} onChange={(event) => setAmount(event.target.value)} />
          </div>
          <div className="rounded-lg border bg-green-50 p-3 text-sm text-green-700">
            จะได้รับ {previewPoints} ⭐ แต้ม
          </div>
          <div className="space-y-2">
            <Label>หมายเหตุ</Label>
            <Input value={note} onChange={(event) => setNote(event.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? "กำลังบันทึก..." : "ยืนยัน"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
