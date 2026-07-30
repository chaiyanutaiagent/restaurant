import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { integrationApi } from "@/lib/integrationApi";
import type { APIKey, ExternalOrder, WebhookEndpoint } from "@/types/integration";
import CreateAPIKeyDialog from "./CreateAPIKeyDialog";
import CreateWebhookDialog from "./CreateWebhookDialog";
import DeliveriesDialog from "./DeliveriesDialog";

const endpointDocs = [
  ["GET", "/api/public/v1/products", "ดึงรายการสินค้า"],
  ["GET", "/api/public/v1/products/{sku}", "ดึงสินค้าตาม SKU"],
  ["GET", "/api/public/v1/stock/{sku}", "ดู stock รวมทุก location"],
  ["POST", "/api/public/v1/orders?source=poolproject", "รับออเดอร์จากระบบภายนอก"],
  ["GET", "/api/public/v1/orders/{external_order_id}?source=poolproject", "ดูสถานะออเดอร์"]
];

const webhookExamples = {
  "sale.created": `{
  "order_number": "SO20260515-0001",
  "total_amount": "200.00",
  "branch_id": "uuid",
  "items_count": 2
}`,
  "stock.low": `{
  "product_id": "uuid",
  "location_id": "uuid",
  "qty_on_hand": "2.0000",
  "min_stock_qty": "5.0000"
}`,
  "product.updated": `{
  "product_id": "uuid",
  "sku": "TEST-001"
}`,
  "order.received": `{
  "external_order_id": "POOL-20260609-001",
  "source": "poolproject",
  "total_amount": "200.00",
  "items_count": 1
}`
};

const incomingOrderExample = `{
  "external_order_id": "POOL-20260609-001",
  "customer_name": "สมชาย ออนไลน์",
  "customer_phone": "0899999999",
  "items": [
    { "sku": "TEST-001", "qty": 2, "unit_price": 100 }
  ],
  "total_amount": 200,
  "payment_method": "credit_card",
  "payment_status": "paid"
}`;

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("th-TH");
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value || 0);
}

export default function IntegrationsPage(): JSX.Element {
  const { toast } = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [apiKeyOpen, setApiKeyOpen] = useState(false);
  const [webhookOpen, setWebhookOpen] = useState(false);
  const [deliveriesOpen, setDeliveriesOpen] = useState(false);
  const [selectedWebhook, setSelectedWebhook] = useState<WebhookEndpoint | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const apiKeysQuery = useQuery({
    queryKey: ["integrations", "api-keys"],
    queryFn: async () => (await integrationApi.listApiKeys()).data.data as APIKey[]
  });
  const webhooksQuery = useQuery({
    queryKey: ["integrations", "webhooks"],
    queryFn: async () => (await integrationApi.listWebhooks()).data.data as WebhookEndpoint[]
  });
  const externalOrdersQuery = useQuery({
    queryKey: ["integrations", "external-orders", statusFilter, sourceFilter],
    queryFn: async () =>
      (await integrationApi.listExternalOrders({
        status: statusFilter || undefined,
        source: sourceFilter.trim() || undefined,
        page: 1,
        limit: 100
      })).data.data as ExternalOrder[]
  });

  const revokeMutation = useMutation({
    mutationFn: async (id: string) => integrationApi.revokeApiKey(id),
    onSuccess: async () => {
      toast({ title: "Revoke API Key แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["integrations", "api-keys"] });
    },
    onError: (error: Error) => {
      toast({ title: "Revoke ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });
  const deleteWebhookMutation = useMutation({
    mutationFn: async (id: string) => integrationApi.deleteWebhook(id),
    onSuccess: async () => {
      toast({ title: "ลบ Webhook แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["integrations", "webhooks"] });
    },
    onError: (error: Error) => {
      toast({ title: "ลบ Webhook ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });
  const testWebhookMutation = useMutation({
    mutationFn: async (id: string) => integrationApi.testWebhook(id),
    onSuccess: async () => {
      toast({ title: "ส่ง test webhook แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["integrations", "webhooks"] });
    },
    onError: (error: Error) => {
      toast({ title: "ทดสอบ Webhook ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });
  const fulfillMutation = useMutation({
    mutationFn: async (id: string) => integrationApi.fulfillExternalOrder(id),
    onSuccess: async () => {
      toast({ title: "เติมออเดอร์แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["integrations", "external-orders"] });
    },
    onError: (error: Error) => {
      toast({ title: "เติมออเดอร์ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const filteredOrders = useMemo(() => {
    return (externalOrdersQuery.data ?? []).filter((order) => {
      const received = new Date(order.received_at);
      const afterFrom = fromDate ? received >= new Date(`${fromDate}T00:00:00`) : true;
      const beforeTo = toDate ? received <= new Date(`${toDate}T23:59:59`) : true;
      return afterFrom && beforeTo;
    });
  }, [externalOrdersQuery.data, fromDate, toDate]);

  return (
    <>
      <PageHeader
        title="การเชื่อมต่อภายนอก"
        subtitle="API Keys + Webhooks"
      />

      <Tabs defaultValue="api-keys" className="space-y-6">
        <TabsList>
          <TabsTrigger value="api-keys">API Keys</TabsTrigger>
          <TabsTrigger value="webhooks">Webhooks</TabsTrigger>
          <TabsTrigger value="orders">ออร์เดอร์จากเว็บ</TabsTrigger>
          <TabsTrigger value="docs">คู่มือ API</TabsTrigger>
        </TabsList>

        <TabsContent value="api-keys">
          <Card>
            <CardContent className="space-y-4 p-4">
              <div className="flex justify-end">
                <Button onClick={() => setApiKeyOpen(true)}>
                  <Plus className="h-4 w-4" />
                  สร้าง API Key
                </Button>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ชื่อ</TableHead>
                    <TableHead>Prefix</TableHead>
                    <TableHead>Scopes</TableHead>
                    <TableHead>ใช้ล่าสุด</TableHead>
                    <TableHead>หมดอายุ</TableHead>
                    <TableHead>สถานะ</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(apiKeysQuery.data ?? []).map((key) => (
                    <TableRow key={key.id}>
                      <TableCell>{key.name}</TableCell>
                      <TableCell className="font-mono">{key.key_prefix}</TableCell>
                      <TableCell className="flex flex-wrap gap-2">
                        {key.scopes.map((scope) => <Badge key={scope} variant="secondary">{scope}</Badge>)}
                      </TableCell>
                      <TableCell>{formatDate(key.last_used_at)}</TableCell>
                      <TableCell>{formatDate(key.expires_at)}</TableCell>
                      <TableCell>
                        <Badge variant={key.is_active && !key.revoked_at ? "success" : "destructive"}>
                          {key.is_active && !key.revoked_at ? "active" : "revoked"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-red-600"
                          disabled={Boolean(key.revoked_at) || revokeMutation.isPending}
                          onClick={() => window.confirm(`ต้องการ revoke ${key.name} หรือไม่`) && revokeMutation.mutate(key.id)}
                        >
                          Revoke
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="webhooks">
          <Card>
            <CardContent className="space-y-4 p-4">
              <div className="flex justify-end">
                <Button onClick={() => setWebhookOpen(true)}>
                  <Plus className="h-4 w-4" />
                  เพิ่ม Webhook
                </Button>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ชื่อ</TableHead>
                    <TableHead>URL</TableHead>
                    <TableHead>Events</TableHead>
                    <TableHead>ครั้งล่าสุด</TableHead>
                    <TableHead>ข้อผิดพลาด</TableHead>
                    <TableHead>สถานะ</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(webhooksQuery.data ?? []).map((webhook) => (
                    <TableRow key={webhook.id}>
                      <TableCell>{webhook.name}</TableCell>
                      <TableCell className="max-w-[280px] truncate">{webhook.url}</TableCell>
                      <TableCell className="flex flex-wrap gap-2">
                        {webhook.events.map((eventName) => <Badge key={eventName} variant="secondary">{eventName}</Badge>)}
                      </TableCell>
                      <TableCell>{formatDate(webhook.last_triggered_at)}</TableCell>
                      <TableCell>
                        <Badge variant={webhook.failure_count > 0 ? "destructive" : "success"}>
                          {webhook.failure_count}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={webhook.is_active ? "success" : "secondary"}>{webhook.is_active ? "active" : "inactive"}</Badge>
                      </TableCell>
                      <TableCell className="space-x-2">
                        <Button variant="outline" size="sm" onClick={() => testWebhookMutation.mutate(webhook.id)}>ทดสอบ</Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setSelectedWebhook(webhook);
                            setDeliveriesOpen(true);
                          }}
                        >
                          ดู Deliveries
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-red-600"
                          onClick={() => window.confirm(`ต้องการลบ ${webhook.name} หรือไม่`) && deleteWebhookMutation.mutate(webhook.id)}
                        >
                          ลบ
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="orders">
          <Card>
            <CardContent className="space-y-4 p-4">
              <div className="flex flex-col gap-3 md:flex-row">
                <select className="h-10 rounded-md border border-gray-300 px-3" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">ทุกสถานะ</option>
                  <option value="pending">pending</option>
                  <option value="fulfilled">fulfilled</option>
                  <option value="cancelled">cancelled</option>
                  <option value="failed">failed</option>
                </select>
                <Input placeholder="source เช่น poolproject" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} />
                <Input type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} />
                <Input type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} />
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>external_order_id</TableHead>
                    <TableHead>แหล่งที่มา</TableHead>
                    <TableHead>ลูกค้า</TableHead>
                    <TableHead>ยอด</TableHead>
                    <TableHead>สถานะชำระ</TableHead>
                    <TableHead>สถานะ</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredOrders.map((order) => (
                    <TableRow key={order.id}>
                      <TableCell className="font-mono">{order.external_order_id}</TableCell>
                      <TableCell>{order.source}</TableCell>
                      <TableCell>{order.customer_name || order.customer_phone || "-"}</TableCell>
                      <TableCell>{formatMoney(order.total_amount)}</TableCell>
                      <TableCell>{order.payment_status || "-"}</TableCell>
                      <TableCell><Badge variant={order.status === "fulfilled" ? "success" : "secondary"}>{order.status}</Badge></TableCell>
                      <TableCell>
                        {order.status === "pending" ? (
                          <Button
                            size="sm"
                            onClick={() => navigate("/logistics", { state: { openCreateShipment: true, externalOrderId: order.id } })}
                          >
                            เติมออเดอร์
                          </Button>
                        ) : order.sale_order_id ? (
                          <Button asChild variant="outline" size="sm">
                            <Link to="/pos">ดูออเดอร์</Link>
                          </Button>
                        ) : (
                          "-"
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="docs">
          <div className="grid gap-6">
            <Card>
              <CardContent className="space-y-3 p-5">
                <h3 className="text-lg font-semibold">Authentication</h3>
                <code className="block rounded-lg bg-slate-950 p-3 text-sm text-slate-100">X-API-Key: erppos_XXXXXXXX_...</code>
                <code className="block rounded-lg bg-slate-950 p-3 text-sm text-slate-100">?api_key=erppos_XXXXXXXX_...</code>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-3 p-5">
                <h3 className="text-lg font-semibold">Endpoints</h3>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Method</TableHead>
                      <TableHead>Endpoint</TableHead>
                      <TableHead>Description</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {endpointDocs.map(([method, path, description]) => (
                      <TableRow key={path}>
                        <TableCell><Badge>{method}</Badge></TableCell>
                        <TableCell className="font-mono text-sm">{path}</TableCell>
                        <TableCell>{description}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-3 p-5">
                <h3 className="text-lg font-semibold">Scopes</h3>
                <div className="flex flex-wrap gap-2">
                  {["products:read", "orders:read", "orders:write", "*"].map((scope) => (
                    <Badge key={scope} variant="secondary">{scope}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-5 p-5">
                <h3 className="text-lg font-semibold">Webhook Events</h3>
                {Object.entries(webhookExamples).map(([eventName, example]) => (
                  <div key={eventName} className="space-y-2">
                    <Badge>{eventName}</Badge>
                    <pre className="overflow-x-auto rounded-lg bg-slate-950 p-4 text-sm text-slate-100">
                      <code>{example}</code>
                    </pre>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-3 p-5">
                <h3 className="text-lg font-semibold">Incoming Orders</h3>
                <p className="font-mono text-sm">POST /webhooks/poolproject/orders</p>
                <p className="text-sm text-gray-500">Signature header: X-ERP-Signature</p>
                <pre className="overflow-x-auto rounded-lg bg-slate-950 p-4 text-sm text-slate-100">
                  <code>{incomingOrderExample}</code>
                </pre>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      <CreateAPIKeyDialog open={apiKeyOpen} onOpenChange={setApiKeyOpen} />
      <CreateWebhookDialog open={webhookOpen} onOpenChange={setWebhookOpen} />
      <DeliveriesDialog open={deliveriesOpen} onOpenChange={setDeliveriesOpen} webhook={selectedWebhook} />
    </>
  );
}
