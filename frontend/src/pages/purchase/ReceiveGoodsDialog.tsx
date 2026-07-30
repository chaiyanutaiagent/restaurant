import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { grApi } from "@/lib/purchaseApi";
import { stockApi } from "@/lib/stockApi";
import type { ApiResponse } from "@/types/api";
import type { GoodsReceipt, PurchaseOrder } from "@/types/purchase";
import type { StockLocation } from "@/types/stock";

type ReceiveGoodsDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  po: PurchaseOrder;
  onSuccess: (receipt: GoodsReceipt) => void;
};

type RowState = Record<string, { qty_received: number; unit_cost: number; note: string }>;

function todayString(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ReceiveGoodsDialog({
  open,
  onOpenChange,
  po,
  onSuccess
}: ReceiveGoodsDialogProps): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [locationId, setLocationId] = useState("");
  const [receivedDate, setReceivedDate] = useState(todayString());
  const [note, setNote] = useState("");
  const [rows, setRows] = useState<RowState>(() =>
    Object.fromEntries(
      po.items.map((item) => [
        item.id,
        {
          qty_received: Math.max(0, Number(item.qty_ordered) - Number(item.qty_received)),
          unit_cost: Number(item.unit_cost),
          note: ""
        }
      ])
    )
  );

  const locationsQuery = useQuery({
    queryKey: ["stock", "locations", "purchase", po.branch_id],
    queryFn: async () => {
      const response = await stockApi.listLocations(po.branch_id);
      return response.data as ApiResponse<StockLocation[]>;
    },
    enabled: open
  });

  const remainingItems = useMemo(
    () =>
      po.items.map((item) => ({
        ...item,
        remaining_qty: Math.max(0, Number(item.qty_ordered) - Number(item.qty_received))
      })),
    [po.items]
  );

  function setRowValue(itemId: string, field: "qty_received" | "unit_cost" | "note", value: number | string): void {
    setRows((prev) => ({
      ...prev,
      [itemId]: { ...prev[itemId], [field]: value }
    }));
  }

  async function submit(): Promise<void> {
    if (!locationId) {
      toast({ title: "กรุณาเลือกคลังที่รับสินค้า", variant: "destructive" });
      return;
    }

    const items = remainingItems
      .map((item) => ({
        po_item_id: item.id,
        product_id: item.product_id,
        variant_id: item.variant_id ?? undefined,
        qty_received: Number(rows[item.id]?.qty_received ?? 0),
        unit_cost: Number(rows[item.id]?.unit_cost ?? 0),
        note: rows[item.id]?.note || undefined,
        remaining_qty: item.remaining_qty
      }))
      .filter((item) => item.qty_received > 0);

    if (items.length === 0) {
      toast({ title: "กรุณาระบุจำนวนรับสินค้าอย่างน้อย 1 รายการ", variant: "destructive" });
      return;
    }

    if (items.some((item) => item.qty_received > item.remaining_qty)) {
      toast({ title: "มีรายการรับเกินจำนวนคงเหลือ", variant: "destructive" });
      return;
    }

    try {
      const response = await grApi.create({
        po_id: po.id,
        location_id: locationId,
        received_date: receivedDate || undefined,
        note: note || undefined,
        items: items.map(({ remaining_qty, ...item }) => item)
      });
      const receipt = (response.data as ApiResponse<GoodsReceipt>).data;
      toast({ title: `รับสินค้าสำเร็จ — GR: ${receipt.gr_number}` });
      await queryClient.invalidateQueries({ queryKey: ["purchase"] });
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
      onSuccess(receipt);
      onOpenChange(false);
    } catch (error) {
      toast({
        title: "รับสินค้าไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-5xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>รับสินค้า — {po.po_number}</DialogTitle>
          <DialogDescription>{po.supplier.name} • วันที่สั่ง {po.order_date}</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="grid gap-2">
            <Label>คลังที่รับสินค้า</Label>
            <select
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              value={locationId}
              onChange={(event) => setLocationId(event.target.value)}
            >
              <option value="">เลือกคลัง</option>
              {(locationsQuery.data?.data ?? []).map((location) => (
                <option key={location.id} value={location.id}>
                  {location.name} ({location.code})
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <Label>วันที่รับ</Label>
            <Input type="date" value={receivedDate} onChange={(event) => setReceivedDate(event.target.value)} />
          </div>
          <div className="grid gap-2 md:col-span-3">
            <Label>หมายเหตุ</Label>
            <textarea
              className="min-h-[88px] rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-600">
              <tr>
                <th className="px-3 py-3">สินค้า</th>
                <th className="px-3 py-3">SKU</th>
                <th className="px-3 py-3">สั่ง</th>
                <th className="px-3 py-3">รับแล้ว</th>
                <th className="px-3 py-3">คงเหลือ</th>
                <th className="px-3 py-3">จำนวนที่รับครั้งนี้*</th>
                <th className="px-3 py-3">ราคาทุน*</th>
              </tr>
            </thead>
            <tbody>
              {remainingItems.map((item) => {
                const row = rows[item.id];
                const isOverReceive = Number(row?.qty_received ?? 0) > item.remaining_qty;
                return (
                  <tr key={item.id} className="border-t">
                    <td className="px-3 py-3">{item.product_name}</td>
                    <td className="px-3 py-3 font-mono text-xs">{item.sku}</td>
                    <td className="px-3 py-3">{item.qty_ordered}</td>
                    <td className="px-3 py-3">{item.qty_received}</td>
                    <td className="px-3 py-3">{item.remaining_qty}</td>
                    <td className="px-3 py-3">
                      <Input
                        type="number"
                        step="0.0001"
                        max={item.remaining_qty}
                        value={row?.qty_received ?? 0}
                        onChange={(event) => setRowValue(item.id, "qty_received", Number(event.target.value))}
                        className={isOverReceive ? "border-red-500" : ""}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <Input
                        type="number"
                        step="0.0001"
                        value={row?.unit_cost ?? 0}
                        onChange={(event) => setRowValue(item.id, "unit_cost", Number(event.target.value))}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            ยกเลิก
          </Button>
          <Button type="button" onClick={() => void submit()}>
            ยืนยันการรับสินค้า
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
