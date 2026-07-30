import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { logisticsApi } from "@/lib/logisticsApi";
import type { Shipment, ShipmentStatus } from "@/types/logistics";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shipment: Shipment | null;
};

const transitions: Record<ShipmentStatus, ShipmentStatus[]> = {
  pending: ["packed", "cancelled"],
  packed: ["picked_up", "cancelled"],
  picked_up: ["in_transit", "returned"],
  in_transit: ["delivered", "returned"],
  delivered: [],
  returned: [],
  cancelled: []
};

export default function StatusUpdateDialog({ open, onOpenChange, shipment }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [nextStatus, setNextStatus] = useState("");
  const [location, setLocation] = useState("");
  const [note, setNote] = useState("");

  const options = useMemo(
    () => (shipment ? transitions[shipment.status] : []),
    [shipment]
  );

  const mutation = useMutation({
    mutationFn: async () => logisticsApi.updateStatus(shipment!.id, { status: nextStatus, location: location || undefined, note: note || undefined }),
    onSuccess: async () => {
      toast({ title: "อัพเดตสถานะแล้ว" });
      onOpenChange(false);
      setNextStatus("");
      setLocation("");
      setNote("");
      await queryClient.invalidateQueries({ queryKey: ["logistics"] });
    },
    onError: (error: Error) => {
      toast({ title: "อัพเดตสถานะไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>อัพเดตสถานะ</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="text-sm text-gray-500">สถานะปัจจุบัน: {shipment?.status || "-"}</div>
          <div className="space-y-2">
            <Label>สถานะใหม่*</Label>
            <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={nextStatus} onChange={(event) => setNextStatus(event.target.value)}>
              <option value="">เลือกสถานะ</option>
              {options.map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>สถานที่</Label>
            <Input value={location} onChange={(event) => setLocation(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>หมายเหตุ</Label>
            <textarea className="min-h-[100px] w-full rounded-md border border-gray-300 px-3 py-2" value={note} onChange={(event) => setNote(event.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => mutation.mutate()} disabled={!nextStatus || mutation.isPending}>
            {mutation.isPending ? "กำลังบันทึก..." : "บันทึก"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
