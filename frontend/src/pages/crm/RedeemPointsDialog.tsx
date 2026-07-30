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
  onRedeemed?: (discountAmount: number) => void;
};

export default function RedeemPointsDialog({ open, onOpenChange, customer, settings, onRedeemed }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [points, setPoints] = useState("");

  useEffect(() => {
    if (!open) {
      setPoints(settings ? String(settings.redeem_min_points) : "");
    }
  }, [open, settings]);

  const discountAmount = useMemo(() => {
    if (!settings) return 0;
    return Number(points || 0) * settings.redeem_rate;
  }, [points, settings]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!customer) throw new Error("ไม่พบสมาชิก");
      return crmApi.redeemPoints({
        customer_id: customer.id,
        points_to_redeem: Number(points || 0)
      });
    },
    onSuccess: async (response) => {
      const data = response.data.data as { discount_amount: number; new_balance: number; points_redeemed: number };
      toast({ title: `แลกแต้มสำเร็จ ส่วนลด ฿${data.discount_amount} คงเหลือ ${data.new_balance} แต้ม` });
      onRedeemed?.(Number(data.discount_amount));
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["crm"] });
    },
    onError: (error: Error) => {
      toast({ title: "แลกแต้มไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>แลกแต้ม</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="rounded-lg border bg-slate-50 p-3 text-sm">
            <div>{customer?.display_name || customer?.first_name || "-"}</div>
            <div>แต้มคงเหลือ: {customer?.points_balance ?? 0} ⭐</div>
          </div>
          <div className="space-y-2">
            <Label>จำนวนแต้มที่แลก</Label>
            <Input type="number" value={points} onChange={(event) => setPoints(event.target.value)} />
          </div>
          <div className="rounded-lg border bg-blue-50 p-3 text-sm text-blue-700">
            มูลค่าส่วนลด: ฿{discountAmount.toFixed(2)}
            {settings && Number(points || 0) < settings.redeem_min_points ? (
              <div className="text-red-600">แต้มต่ำกว่าขั้นต่ำที่กำหนด</div>
            ) : null}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? "กำลังแลก..." : "ยืนยัน"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
