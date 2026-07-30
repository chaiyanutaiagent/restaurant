import { useQuery } from "@tanstack/react-query";
import { Plus, Truck } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermission } from "@/hooks/usePermission";
import { logisticsApi } from "@/lib/logisticsApi";
import type { Carrier, Shipment, ShipmentListItem } from "@/types/logistics";
import CreateShipmentDialog from "./CreateShipmentDialog";
import ShipmentDetailDialog from "./ShipmentDetailDialog";
import StatusUpdateDialog from "./StatusUpdateDialog";

type LocationState = {
  openCreateShipment?: boolean;
  externalOrderId?: string | null;
};

const statusMeta: Record<string, { label: string; className: string }> = {
  pending: { label: "รอดำเนินการ", className: "bg-gray-100 text-gray-700" },
  packed: { label: "จัดแพ็คแล้ว", className: "bg-blue-100 text-blue-700" },
  picked_up: { label: "รับพัสดุแล้ว", className: "bg-purple-100 text-purple-700" },
  in_transit: { label: "กำลังส่ง", className: "bg-orange-100 text-orange-700" },
  delivered: { label: "ส่งแล้ว", className: "bg-green-100 text-green-700" },
  returned: { label: "คืนสินค้า", className: "bg-red-100 text-red-700" },
  cancelled: { label: "ยกเลิก", className: "bg-slate-100 text-slate-700" }
};

const carrierColors: Record<string, string> = {
  THPOST: "bg-indigo-100 text-indigo-700",
  FLASH: "bg-yellow-100 text-yellow-800",
  JT: "bg-emerald-100 text-emerald-700",
  KERRY: "bg-orange-100 text-orange-700"
};

function formatMoney(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value || 0);
}

function saveBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

export default function ShipmentsPage(): JSX.Element {
  const canCreate = usePermission("pos.sale.create");
  const location = useLocation();
  const state = (location.state as LocationState | null) ?? null;
  const [carrierFilter, setCarrierFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(Boolean(state?.openCreateShipment));
  const [detailId, setDetailId] = useState<string | null>(null);
  const [statusShipment, setStatusShipment] = useState<Shipment | null>(null);

  const carriersQuery = useQuery({
    queryKey: ["logistics", "carriers"],
    queryFn: async () => (await logisticsApi.listCarriers()).data.data as Carrier[]
  });
  const shipmentsQuery = useQuery({
    queryKey: ["logistics", "shipments", { carrierFilter, statusFilter, dateFrom, dateTo, search }],
    queryFn: async () =>
      (await logisticsApi.listShipments({
        carrier_id: carrierFilter || undefined,
        status: statusFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        search: search || undefined,
        page: 1,
        limit: 100
      })).data.data as ShipmentListItem[]
  });

  const summary = useMemo(() => {
    const counts = {
      pending: 0,
      packed: 0,
      picked_up: 0,
      in_transit: 0,
      delivered: 0,
      returned: 0
    };
    for (const shipment of shipmentsQuery.data ?? []) {
      if (shipment.status in counts) counts[shipment.status as keyof typeof counts] += 1;
    }
    return counts;
  }, [shipmentsQuery.data]);

  async function printLabel(shipmentId: string): Promise<void> {
    const response = await logisticsApi.downloadLabel(shipmentId);
    saveBlob(response.data as Blob, `label_${shipmentId}.pdf`);
  }

  return (
    <>
      <PageHeader
        title="การจัดส่ง"
        subtitle="Shipment Management"
        actions={canCreate ? (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            สร้างการจัดส่ง
          </Button>
        ) : null}
      />

      <div className="mb-6 flex flex-wrap gap-2">
        {[
          ["pending", summary.pending],
          ["packed", summary.packed],
          ["picked_up", summary.picked_up],
          ["in_transit", summary.in_transit],
          ["delivered", summary.delivered],
          ["returned", summary.returned]
        ].map(([status, count]) => (
          <Badge key={status} className={statusMeta[status].className}>
            {statusMeta[status].label}: {count}
          </Badge>
        ))}
      </div>

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              {(carriersQuery.data ?? []).map((carrier) => (
                <button
                  key={carrier.id}
                  type="button"
                  className={`rounded-full px-3 py-1 text-sm ${carrierFilter === carrier.id ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-700"}`}
                  onClick={() => setCarrierFilter((current) => current === carrier.id ? "" : carrier.id)}
                >
                  {carrier.name}
                </button>
              ))}
            </div>
            <div className="grid gap-3 md:grid-cols-5">
              <select className="h-10 rounded-md border border-gray-300 px-3" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">ทุกสถานะ</option>
                {Object.entries(statusMeta).map(([status, meta]) => (
                  <option key={status} value={status}>{meta.label}</option>
                ))}
              </select>
              <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
              <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
              <Input className="md:col-span-2" placeholder="ค้นหา tracking / ผู้รับ" value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>เลขที่จัดส่ง</TableHead>
                <TableHead>ผู้รับ</TableHead>
                <TableHead>Carrier</TableHead>
                <TableHead>เลขพัสดุ</TableHead>
                <TableHead>น้ำหนัก</TableHead>
                <TableHead>COD</TableHead>
                <TableHead>ค่าส่ง</TableHead>
                <TableHead>สถานะ</TableHead>
                <TableHead>วันที่สร้าง</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(shipmentsQuery.data ?? []).map((shipment) => (
                <TableRow key={shipment.id}>
                  <TableCell>
                    <button type="button" className="font-mono text-blue-600 underline" onClick={() => setDetailId(shipment.id)}>
                      {shipment.shipment_number}
                    </button>
                  </TableCell>
                  <TableCell>{shipment.recipient_name}<div className="text-xs text-gray-500">{shipment.recipient_phone}</div></TableCell>
                  <TableCell>
                    <Badge className={carrierColors[shipment.carrier_code] || "bg-slate-100 text-slate-700"}>{shipment.carrier_name}</Badge>
                  </TableCell>
                  <TableCell className="font-mono">
                    {shipment.tracking_number ? (
                      <span>{shipment.tracking_number}</span>
                    ) : "-"}
                  </TableCell>
                  <TableCell>{shipment.weight_grams} g</TableCell>
                  <TableCell>{shipment.is_cod ? <Badge variant="destructive">COD {formatMoney(shipment.cod_amount)}</Badge> : "-"}</TableCell>
                  <TableCell>{formatMoney(shipment.shipping_cost)}</TableCell>
                  <TableCell><Badge className={statusMeta[shipment.status].className}>{statusMeta[shipment.status].label}</Badge></TableCell>
                  <TableCell>{new Date(shipment.created_at).toLocaleDateString("th-TH")}</TableCell>
                  <TableCell className="space-x-2">
                    <Button variant="outline" size="sm" onClick={() => setDetailId(shipment.id)}>ดูรายละเอียด</Button>
                    <Button variant="outline" size="sm" onClick={() => void printLabel(shipment.id)}>พิมพ์ Label</Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setStatusShipment({
                          id: shipment.id,
                          shipment_number: shipment.shipment_number,
                          status: shipment.status,
                          branch_id: "",
                          carrier_id: "",
                          carrier_name: shipment.carrier_name,
                          carrier_code: shipment.carrier_code,
                          tracking_url: null,
                          sale_order_id: null,
                          external_order_id: null,
                          sender_name: "",
                          sender_phone: "",
                          sender_address: "",
                          recipient_name: shipment.recipient_name,
                          recipient_phone: shipment.recipient_phone,
                          recipient_address: "",
                          weight_grams: shipment.weight_grams,
                          service_name: null,
                          is_cod: shipment.is_cod,
                          cod_amount: shipment.cod_amount,
                          shipping_cost: shipment.shipping_cost,
                          tracking_number: shipment.tracking_number,
                          picked_up_at: null,
                          delivered_at: null,
                          note: null,
                          created_at: shipment.created_at,
                          items: [],
                          events: []
                        })
                      }
                    >
                      อัพเดตสถานะ
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <CreateShipmentDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        initialExternalOrderId={state?.externalOrderId ?? null}
      />
      <ShipmentDetailDialog
        open={Boolean(detailId)}
        onOpenChange={(open) => !open && setDetailId(null)}
        shipmentId={detailId}
        onPrintLabel={(shipmentId) => void printLabel(shipmentId)}
        onUpdateStatus={(shipment) => setStatusShipment(shipment)}
      />
      <StatusUpdateDialog open={Boolean(statusShipment)} onOpenChange={(open) => !open && setStatusShipment(null)} shipment={statusShipment} />
    </>
  );
}
