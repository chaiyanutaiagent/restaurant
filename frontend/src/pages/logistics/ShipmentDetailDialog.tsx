import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { logisticsApi } from "@/lib/logisticsApi";
import type { Shipment } from "@/types/logistics";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shipmentId: string | null;
  onPrintLabel: (shipmentId: string) => void;
  onUpdateStatus: (shipment: Shipment) => void;
};

const statusLabel: Record<string, string> = {
  pending: "รอดำเนินการ",
  packed: "แพ็คสินค้าแล้ว",
  picked_up: "รับพัสดุแล้ว",
  in_transit: "กำลังส่ง",
  delivered: "ส่งแล้ว",
  returned: "คืนสินค้า",
  cancelled: "ยกเลิก"
};

export default function ShipmentDetailDialog({
  open,
  onOpenChange,
  shipmentId,
  onPrintLabel,
  onUpdateStatus
}: Props): JSX.Element {
  const shipmentQuery = useQuery({
    queryKey: ["logistics", "shipment", shipmentId],
    enabled: open && Boolean(shipmentId),
    queryFn: async () => (await logisticsApi.getShipment(shipmentId!)).data.data as Shipment
  });

  const shipment = shipmentQuery.data ?? null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-6xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{shipment?.shipment_number || "Shipment Detail"}</DialogTitle>
        </DialogHeader>

        {shipment ? (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-full bg-blue-100 px-3 py-1 text-sm text-blue-700">{shipment.carrier_name}</span>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700">{statusLabel[shipment.status] || shipment.status}</span>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border p-4">
                <div className="mb-2 font-semibold">ผู้ส่ง</div>
                <div>{shipment.sender_name}</div>
                <div>{shipment.sender_phone}</div>
                <div className="whitespace-pre-wrap text-sm text-gray-600">{shipment.sender_address}</div>
              </div>
              <div className="rounded-xl border p-4">
                <div className="mb-2 font-semibold">ผู้รับ</div>
                <div>{shipment.recipient_name}</div>
                <div>{shipment.recipient_phone}</div>
                <div className="whitespace-pre-wrap text-sm text-gray-600">{shipment.recipient_address}</div>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-4">
              <div className="rounded-xl border p-4">น้ำหนัก: {shipment.weight_grams} g</div>
              <div className="rounded-xl border p-4">ค่าส่ง: ฿{shipment.shipping_cost}</div>
              <div className="rounded-xl border p-4">เลขพัสดุ: {shipment.tracking_number || "-"}</div>
              <div className="rounded-xl border p-4">{shipment.is_cod ? `COD ฿${shipment.cod_amount}` : "ไม่ใช่ COD"}</div>
            </div>

            {shipment.tracking_url ? (
              <a className="text-sm font-medium text-blue-600 underline" href={shipment.tracking_url} target="_blank" rel="noreferrer">
                เปิดลิงก์ติดตามพัสดุ
              </a>
            ) : null}

            <div>
              <div className="mb-2 font-semibold">รายการสินค้า</div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>สินค้า</TableHead>
                    <TableHead>SKU</TableHead>
                    <TableHead>จำนวน</TableHead>
                    <TableHead>ราคา</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shipment.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.product_name}</TableCell>
                      <TableCell>{item.sku || "-"}</TableCell>
                      <TableCell>{item.qty}</TableCell>
                      <TableCell>{item.unit_price ?? "-"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <div>
              <div className="mb-3 font-semibold">ประวัติการจัดส่ง</div>
              <div className="space-y-4">
                {shipment.events.map((event) => (
                  <div key={event.id} className="flex gap-3">
                    <div className="mt-1 h-3 w-3 rounded-full bg-blue-500" />
                    <div>
                      <div className="font-medium">{statusLabel[event.status] || event.status}</div>
                      <div className="text-sm text-gray-500">
                        {[event.location, new Date(event.event_at).toLocaleString("th-TH")].filter(Boolean).join(" • ")}
                      </div>
                      {event.note ? <div className="text-sm text-gray-600">{event.note}</div> : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="outline" onClick={() => onPrintLabel(shipment.id)}>พิมพ์ Label</Button>
              <Button variant="outline" onClick={() => onUpdateStatus(shipment)}>อัพเดตสถานะ</Button>
              <Button onClick={() => onOpenChange(false)}>ปิด</Button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
