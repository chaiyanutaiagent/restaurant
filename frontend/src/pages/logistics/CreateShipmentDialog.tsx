import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import api from "@/lib/api";
import { integrationApi } from "@/lib/integrationApi";
import { logisticsApi } from "@/lib/logisticsApi";
import type { ExternalOrder } from "@/types/integration";
import type { Carrier, Shipment, ShippingEstimate } from "@/types/logistics";

type SaleListItem = {
  id: string;
  order_number: string;
  customer_name: string | null;
  customer_phone: string | null;
  total_amount: number;
  items: Array<{
    product_id: string;
    product_name: string;
    sku: string | null;
    qty: number;
    unit_price: number;
  }>;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialExternalOrderId?: string | null;
  onCreated?: (shipment: Shipment) => void;
};

type SourceType = "sale" | "external" | "manual";

const steps = ["source", "recipient", "package", "service"] as const;

function normalizeAddress(value: string | null | undefined): string {
  return value?.trim() || "-";
}

export default function CreateShipmentDialog({
  open,
  onOpenChange,
  initialExternalOrderId,
  onCreated
}: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [stepIndex, setStepIndex] = useState(0);
  const [sourceType, setSourceType] = useState<SourceType>("manual");
  const [selectedSaleOrderId, setSelectedSaleOrderId] = useState("");
  const [selectedExternalOrderId, setSelectedExternalOrderId] = useState(initialExternalOrderId ?? "");
  const [saleSearch, setSaleSearch] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [recipientPhone, setRecipientPhone] = useState("");
  const [recipientAddress, setRecipientAddress] = useState("");
  const [weightGrams, setWeightGrams] = useState("500");
  const [widthCm, setWidthCm] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [depthCm, setDepthCm] = useState("");
  const [carrierId, setCarrierId] = useState("");
  const [serviceName, setServiceName] = useState("");
  const [isCod, setIsCod] = useState(false);
  const [codAmount, setCodAmount] = useState("0");
  const [shippingCost, setShippingCost] = useState("0");
  const [trackingNumber, setTrackingNumber] = useState("");
  const [autoGenerateTracking, setAutoGenerateTracking] = useState(true);
  const [note, setNote] = useState("");

  const carriersQuery = useQuery({
    queryKey: ["logistics", "carriers"],
    queryFn: async () => (await logisticsApi.listCarriers()).data.data as Carrier[]
  });
  const externalOrdersQuery = useQuery({
    queryKey: ["logistics", "external-orders", "pending"],
    enabled: open,
    queryFn: async () =>
      (await integrationApi.listExternalOrders({ status: "pending", page: 1, limit: 100 })).data.data as ExternalOrder[]
  });
  const saleOrdersQuery = useQuery({
    queryKey: ["logistics", "sales"],
    enabled: open,
    queryFn: async () => (await api.get("/pos/sales", { params: { page: 1, limit: 100 } })).data.data as SaleListItem[]
  });

  const selectedSale = useMemo(
    () => (saleOrdersQuery.data ?? []).find((item) => item.id === selectedSaleOrderId) ?? null,
    [saleOrdersQuery.data, selectedSaleOrderId]
  );
  const selectedExternal = useMemo(
    () => (externalOrdersQuery.data ?? []).find((item) => item.id === selectedExternalOrderId) ?? null,
    [externalOrdersQuery.data, selectedExternalOrderId]
  );
  const filteredSales = useMemo(() => {
    const keyword = saleSearch.trim().toLowerCase();
    if (!keyword) return saleOrdersQuery.data ?? [];
    return (saleOrdersQuery.data ?? []).filter((item) =>
      [item.order_number, item.customer_name ?? "", item.customer_phone ?? ""].join(" ").toLowerCase().includes(keyword)
    );
  }, [saleOrdersQuery.data, saleSearch]);

  useEffect(() => {
    if (!open) {
      setStepIndex(0);
      setSourceType(initialExternalOrderId ? "external" : "manual");
      setSelectedSaleOrderId("");
      setSelectedExternalOrderId(initialExternalOrderId ?? "");
      setSaleSearch("");
      setRecipientName("");
      setRecipientPhone("");
      setRecipientAddress("");
      setWeightGrams("500");
      setWidthCm("");
      setHeightCm("");
      setDepthCm("");
      setCarrierId("");
      setServiceName("");
      setIsCod(false);
      setCodAmount("0");
      setShippingCost("0");
      setTrackingNumber("");
      setAutoGenerateTracking(true);
      setNote("");
    }
  }, [open, initialExternalOrderId]);

  useEffect(() => {
    if (initialExternalOrderId && open) {
      setSourceType("external");
      setSelectedExternalOrderId(initialExternalOrderId);
    }
  }, [initialExternalOrderId, open]);

  useEffect(() => {
    if (sourceType === "sale" && selectedSale) {
      setRecipientName(selectedSale.customer_name || "");
      setRecipientPhone(selectedSale.customer_phone || "");
      setRecipientAddress("-");
    } else if (sourceType === "external" && selectedExternal) {
      setRecipientName(selectedExternal.customer_name || "");
      setRecipientPhone(selectedExternal.customer_phone || "");
      setRecipientAddress("-");
      setIsCod(selectedExternal.payment_status === "unpaid");
      setCodAmount(String(selectedExternal.total_amount || 0));
    }
  }, [selectedSale, selectedExternal, sourceType]);

  const estimateMutation = useMutation({
    mutationFn: async () =>
      logisticsApi.estimate({
        weight_grams: Number(weightGrams || 0),
        zone: recipientAddress.includes("กรุงเทพ") ? "bangkok" : "all",
        is_cod: isCod
      }),
    onError: (error: Error) => {
      toast({ title: "คำนวณค่าส่งไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const items =
        sourceType === "sale" && selectedSale
          ? selectedSale.items.map((item) => ({
              product_id: item.product_id,
              product_name: item.product_name,
              sku: item.sku,
              qty: item.qty,
              unit_price: item.unit_price
            }))
          : sourceType === "external" && selectedExternal
            ? [
                {
                  product_name: selectedExternal.external_order_id,
                  sku: null,
                  qty: 1,
                  unit_price: selectedExternal.total_amount
                }
              ]
            : [
                {
                  product_name: "สินค้าทดสอบ",
                  sku: "MANUAL",
                  qty: 1,
                  unit_price: 0
                }
              ];
      return logisticsApi.createShipment({
        branch_id: "",
        carrier_id: carrierId,
        service_name: serviceName || null,
        sale_order_id: sourceType === "sale" ? selectedSaleOrderId || null : null,
        external_order_id: sourceType === "external" ? selectedExternalOrderId || null : null,
        recipient_name: recipientName,
        recipient_phone: recipientPhone,
        recipient_address: normalizeAddress(recipientAddress),
        weight_grams: Number(weightGrams || 0),
        width_cm: widthCm ? Number(widthCm) : null,
        height_cm: heightCm ? Number(heightCm) : null,
        depth_cm: depthCm ? Number(depthCm) : null,
        is_cod: isCod,
        cod_amount: Number(codAmount || 0),
        shipping_cost: Number(shippingCost || 0),
        tracking_number: autoGenerateTracking ? null : trackingNumber || null,
        note: note || null,
        items
      });
    },
    onSuccess: async (response) => {
      const shipment = response.data.data as Shipment;
      toast({ title: `สร้างการจัดส่งแล้ว: ${shipment.shipment_number}` });
      onCreated?.(shipment);
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["logistics"] });
    },
    onError: (error: Error) => {
      toast({ title: "สร้างการจัดส่งไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const estimates = (estimateMutation.data?.data.data ?? []) as ShippingEstimate[];
  const selectedCarrier = (carriersQuery.data ?? []).find((item) => item.id === carrierId) ?? null;

  async function createShipment(): Promise<void> {
    const branchResp = await api.get("/system/branches");
    const branchId = branchResp.data.data[0]?.id;
    if (!branchId) {
      toast({ title: "ไม่พบสาขาเริ่มต้น", variant: "destructive" });
      return;
    }
    createMutation.mutateAsync = createMutation.mutateAsync.bind(createMutation);
    const items =
      sourceType === "sale" && selectedSale
        ? selectedSale.items.map((item) => ({
            product_id: item.product_id,
            product_name: item.product_name,
            sku: item.sku,
            qty: item.qty,
            unit_price: item.unit_price
          }))
        : sourceType === "external" && selectedExternal
          ? [
              {
                product_name: selectedExternal.external_order_id,
                sku: null,
                qty: 1,
                unit_price: selectedExternal.total_amount
              }
            ]
          : [
              {
                product_name: "สินค้าทดสอบ",
                sku: "MANUAL",
                qty: 1,
                unit_price: 0
              }
            ];
    try {
      const response = await logisticsApi.createShipment({
        branch_id: branchId,
        carrier_id: carrierId,
        service_name: serviceName || null,
        sale_order_id: sourceType === "sale" ? selectedSaleOrderId || null : null,
        external_order_id: sourceType === "external" ? selectedExternalOrderId || null : null,
        recipient_name: recipientName,
        recipient_phone: recipientPhone,
        recipient_address: normalizeAddress(recipientAddress),
        weight_grams: Number(weightGrams || 0),
        width_cm: widthCm ? Number(widthCm) : null,
        height_cm: heightCm ? Number(heightCm) : null,
        depth_cm: depthCm ? Number(depthCm) : null,
        is_cod: isCod,
        cod_amount: Number(codAmount || 0),
        shipping_cost: Number(shippingCost || 0),
        tracking_number: autoGenerateTracking ? null : trackingNumber || null,
        note: note || null,
        items
      });
      const shipment = response.data.data as Shipment;
      toast({ title: `สร้างการจัดส่งแล้ว: ${shipment.shipment_number}` });
      onCreated?.(shipment);
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["logistics"] });
    } catch (error) {
      toast({ title: "สร้างการจัดส่งไม่สำเร็จ", description: error instanceof Error ? error.message : "Unknown error", variant: "destructive" });
    }
  }

  function canContinueSource(): boolean {
    if (sourceType === "sale") return Boolean(selectedSaleOrderId);
    if (sourceType === "external") return Boolean(selectedExternalOrderId);
    return true;
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-6xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>สร้างการจัดส่ง</DialogTitle>
        </DialogHeader>

        <div className="flex gap-2">
          {steps.map((step, index) => (
            <div key={step} className={`rounded-full px-3 py-1 text-sm ${index === stepIndex ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600"}`}>
              {index + 1}. {step}
            </div>
          ))}
        </div>

        {stepIndex === 0 ? (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <label className={`rounded-lg border p-4 ${sourceType === "sale" ? "border-blue-500 bg-blue-50" : ""}`}>
                <input type="radio" className="mr-2" checked={sourceType === "sale"} onChange={() => setSourceType("sale")} />
                จาก Sale Order
              </label>
              <label className={`rounded-lg border p-4 ${sourceType === "external" ? "border-blue-500 bg-blue-50" : ""}`}>
                <input type="radio" className="mr-2" checked={sourceType === "external"} onChange={() => setSourceType("external")} />
                จาก Web Order
              </label>
              <label className={`rounded-lg border p-4 ${sourceType === "manual" ? "border-blue-500 bg-blue-50" : ""}`}>
                <input type="radio" className="mr-2" checked={sourceType === "manual"} onChange={() => setSourceType("manual")} />
                สร้างใหม่
              </label>
            </div>

            {sourceType === "sale" ? (
              <div className="space-y-3">
                <Input placeholder="ค้นหา order_number / ลูกค้า / เบอร์โทร" value={saleSearch} onChange={(event) => setSaleSearch(event.target.value)} />
                <div className="max-h-72 overflow-y-auto rounded-lg border">
                  {filteredSales.map((order) => (
                    <button
                      key={order.id}
                      type="button"
                      className={`flex w-full items-center justify-between border-b px-4 py-3 text-left last:border-b-0 ${selectedSaleOrderId === order.id ? "bg-blue-50" : ""}`}
                      onClick={() => setSelectedSaleOrderId(order.id)}
                    >
                      <div>
                        <div className="font-mono text-sm">{order.order_number}</div>
                        <div className="text-sm text-gray-500">{order.customer_name || "-"} • {order.customer_phone || "-"}</div>
                      </div>
                      <div>{new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(order.total_amount || 0)}</div>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {sourceType === "external" ? (
              <div className="max-h-72 overflow-y-auto rounded-lg border">
                {(externalOrdersQuery.data ?? []).map((order) => (
                  <button
                    key={order.id}
                    type="button"
                    className={`flex w-full items-center justify-between border-b px-4 py-3 text-left last:border-b-0 ${selectedExternalOrderId === order.id ? "bg-blue-50" : ""}`}
                    onClick={() => setSelectedExternalOrderId(order.id)}
                  >
                    <div>
                      <div className="font-mono text-sm">{order.external_order_id}</div>
                      <div className="text-sm text-gray-500">{order.customer_name || "-"} • {order.customer_phone || "-"}</div>
                    </div>
                    <div>{new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(order.total_amount || 0)}</div>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {stepIndex === 1 ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>ชื่อผู้รับ*</Label>
              <Input value={recipientName} onChange={(event) => setRecipientName(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>เบอร์โทร*</Label>
              <Input value={recipientPhone} onChange={(event) => setRecipientPhone(event.target.value)} />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label>ที่อยู่จัดส่ง*</Label>
              <textarea className="min-h-[120px] w-full rounded-md border border-gray-300 px-3 py-2" value={recipientAddress} onChange={(event) => setRecipientAddress(event.target.value)} />
            </div>
          </div>
        ) : null}

        {stepIndex === 2 ? (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-4">
              <div className="space-y-2">
                <Label>น้ำหนัก (กรัม)*</Label>
                <Input type="number" value={weightGrams} onChange={(event) => setWeightGrams(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>กว้าง (ซม.)</Label>
                <Input type="number" value={widthCm} onChange={(event) => setWidthCm(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>สูง (ซม.)</Label>
                <Input type="number" value={heightCm} onChange={(event) => setHeightCm(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>ลึก (ซม.)</Label>
                <Input type="number" value={depthCm} onChange={(event) => setDepthCm(event.target.value)} />
              </div>
            </div>
            <div className="flex justify-end">
              <Button onClick={() => estimateMutation.mutate()}>คำนวณค่าส่ง</Button>
            </div>
            {estimates.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Carrier</TableHead>
                    <TableHead>Service</TableHead>
                    <TableHead>Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {estimates.map((estimate, index) => (
                    <TableRow
                      key={`${estimate.carrier_id}-${estimate.service_name}`}
                      className="cursor-pointer"
                      onClick={() => {
                        setCarrierId(estimate.carrier_id);
                        setServiceName(estimate.service_name);
                        setShippingCost(String(estimate.cost));
                      }}
                    >
                      <TableCell>{estimate.carrier_name}{index === 0 ? " ← cheapest" : ""}</TableCell>
                      <TableCell>{estimate.service_name}</TableCell>
                      <TableCell>{new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(estimate.cost || 0)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
          </div>
        ) : null}

        {stepIndex === 3 ? (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Carrier</Label>
                <select className="h-10 w-full rounded-md border border-gray-300 px-3" value={carrierId} onChange={(event) => setCarrierId(event.target.value)}>
                  <option value="">เลือก Carrier</option>
                  {(carriersQuery.data ?? []).map((carrier) => (
                    <option key={carrier.id} value={carrier.id}>{carrier.name}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label>Service name</Label>
                <Input value={serviceName} onChange={(event) => setServiceName(event.target.value)} placeholder={selectedCarrier?.code === "FLASH" ? "Flash Standard" : ""} />
              </div>
              <div className="space-y-2">
                <Label>ค่าจัดส่ง</Label>
                <Input type="number" value={shippingCost} onChange={(event) => setShippingCost(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>COD amount</Label>
                <Input type="number" value={codAmount} onChange={(event) => setCodAmount(event.target.value)} disabled={!isCod} />
              </div>
            </div>

            <label className="flex items-center gap-3">
              <Checkbox checked={isCod} onCheckedChange={(checked) => setIsCod(checked === true)} />
              <span>COD</span>
            </label>

            <label className="flex items-center gap-3">
              <Checkbox checked={autoGenerateTracking} onCheckedChange={(checked) => setAutoGenerateTracking(checked === true)} />
              <span>สร้างอัตโนมัติ</span>
            </label>

            <div className="space-y-2">
              <Label>เลขพัสดุ</Label>
              <Input value={trackingNumber} onChange={(event) => setTrackingNumber(event.target.value)} disabled={autoGenerateTracking} />
            </div>

            <div className="space-y-2">
              <Label>หมายเหตุ</Label>
              <textarea className="min-h-[100px] w-full rounded-md border border-gray-300 px-3 py-2" value={note} onChange={(event) => setNote(event.target.value)} />
            </div>

            <div className="rounded-lg border bg-slate-50 p-4 text-sm">
              <div className="font-medium">Confirm summary</div>
              <div>ผู้รับ: {recipientName || "-"}</div>
              <div>Carrier: {selectedCarrier?.name || "-"}</div>
              <div>ค่าส่ง: {shippingCost || "0"}</div>
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => stepIndex === 0 ? onOpenChange(false) : setStepIndex((current) => current - 1)}>
            {stepIndex === 0 ? "ยกเลิก" : "ย้อนกลับ"}
          </Button>
          {stepIndex < steps.length - 1 ? (
            <Button
              onClick={() => setStepIndex((current) => current + 1)}
              disabled={
                (stepIndex === 0 && !canContinueSource())
                || (stepIndex === 1 && (!recipientName.trim() || !recipientPhone.trim() || !recipientAddress.trim()))
              }
            >
              ถัดไป
            </Button>
          ) : (
            <Button onClick={() => void createShipment()} disabled={!carrierId || !recipientName.trim()}>
              สร้างการจัดส่ง
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
