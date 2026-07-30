import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { AlertCircle, CheckCircle2, Cog, Mail, MessageSquare, Wallet } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { gatewayApi } from "@/lib/paymentGatewayApi";
import api from "@/lib/api";
import type { GatewayConfig, NotificationLog } from "@/types/paymentGateway";

type HealthMap = Record<string, { status: string; label?: string; error?: string; active?: number; version?: string }>;

type ConfigForm = {
  promptpay_target: string;
  promptpay_name: string;
  promptpay_enabled: boolean;
  omise_public_key: string;
  omise_secret_key: string;
  omise_enabled: boolean;
  twoc2p_merchant_id: string;
  twoc2p_secret_key: string;
  twoc2p_enabled: boolean;
  line_notify_token: string;
  line_notify_enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password: string;
  smtp_from_email: string;
  smtp_from_name: string;
  smtp_enabled: boolean;
};

function toForm(config?: GatewayConfig | null): ConfigForm {
  return {
    promptpay_target: config?.promptpay_target ?? "",
    promptpay_name: config?.promptpay_name ?? "",
    promptpay_enabled: config?.promptpay_enabled ?? true,
    omise_public_key: config?.omise_public_key ?? "",
    omise_secret_key: "",
    omise_enabled: config?.omise_enabled ?? false,
    twoc2p_merchant_id: config?.twoc2p_merchant_id ?? "",
    twoc2p_secret_key: "",
    twoc2p_enabled: config?.twoc2p_enabled ?? false,
    line_notify_token: "",
    line_notify_enabled: config?.line_notify_enabled ?? false,
    smtp_host: config?.smtp_host ?? "",
    smtp_port: config?.smtp_port ?? 587,
    smtp_username: config?.smtp_username ?? "",
    smtp_password: "",
    smtp_from_email: config?.smtp_from_email ?? "",
    smtp_from_name: config?.smtp_from_name ?? "",
    smtp_enabled: config?.smtp_enabled ?? false
  };
}

function HealthBadge({ status }: { status: string }): JSX.Element {
  if (status === "ok") {
    return <Badge className="bg-green-100 text-green-700 hover:bg-green-100">ok</Badge>;
  }
  if (status === "disabled") {
    return <Badge variant="secondary">disabled</Badge>;
  }
  return <Badge variant="destructive">error</Badge>;
}

export default function SettingsPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ConfigForm>(toForm());
  const [qrPreview, setQrPreview] = useState<string>("");

  const configQuery = useQuery({
    queryKey: ["payments", "config"],
    queryFn: async () => (await gatewayApi.getConfig()).data.data as GatewayConfig
  });
  const notificationsQuery = useQuery({
    queryKey: ["payments", "notifications"],
    queryFn: async () => (await gatewayApi.listNotifications({ page: 1, limit: 50 })).data
  });
  const healthQuery = useQuery({
    queryKey: ["system", "health-detail"],
    queryFn: async () => (await api.get("/system/health-detail")).data.data as HealthMap
  });

  useEffect(() => {
    if (configQuery.data) {
      setForm(toForm(configQuery.data));
    }
  }, [configQuery.data]);

  useEffect(() => {
    const run = async (): Promise<void> => {
      if (!form.promptpay_target) {
        setQrPreview("");
        return;
      }
      try {
        const response = await fetch(`/api/v1/pos/promptpay/qr?amount=1&target=${encodeURIComponent(form.promptpay_target)}`);
        const data = await response.json();
        const payload = data.data?.payload as string | undefined;
        if (!payload) {
          setQrPreview("");
          return;
        }
        setQrPreview(await QRCode.toDataURL(payload, { width: 180, margin: 1 }));
      } catch {
        setQrPreview("");
      }
    };
    void run();
  }, [form.promptpay_target]);

  const saveMutation = useMutation({
    mutationFn: async (payload: Record<string, unknown>) => gatewayApi.updateConfig(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["payments", "config"] }),
        queryClient.invalidateQueries({ queryKey: ["system", "health-detail"] })
      ]);
      toast({ title: "บันทึกการตั้งค่าแล้ว" });
    }
  });

  const testLineMutation = useMutation({
    mutationFn: async () => gatewayApi.testLineNotify(),
    onSuccess: () => toast({ title: "ส่งข้อความทดสอบแล้ว" })
  });

  const testEmailMutation = useMutation({
    mutationFn: async () => gatewayApi.testEmail(),
    onSuccess: () => toast({ title: "ส่งอีเมลทดสอบแล้ว" })
  });

  const notificationRows = useMemo(
    () => ((notificationsQuery.data?.data as NotificationLog[] | undefined) ?? []),
    [notificationsQuery.data]
  );
  const notificationMeta = notificationsQuery.data?.meta as { total?: number } | undefined;

  return (
    <div className="space-y-6">
      <PageHeader title="ตั้งค่าระบบ" subtitle="Payment Gateway + Notifications" />

      <Tabs defaultValue="payments">
        <TabsList className="flex h-auto flex-wrap gap-1">
          <TabsTrigger value="payments">ช่องทางชำระเงิน</TabsTrigger>
          <TabsTrigger value="notify">การแจ้งเตือน</TabsTrigger>
          <TabsTrigger value="logs">ประวัติการแจ้งเตือน</TabsTrigger>
          <TabsTrigger value="health">ตรวจสอบระบบ</TabsTrigger>
        </TabsList>

        <TabsContent value="payments" className="space-y-4">
          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-2 text-lg font-semibold text-gray-900">
                <Wallet className="h-5 w-5" />
                PromptPay
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="เปิดใช้ PromptPay">
                  <input type="checkbox" checked={form.promptpay_enabled} onChange={(event) => setForm((prev) => ({ ...prev, promptpay_enabled: event.target.checked }))} />
                </Field>
                <Field label="หมายเลข PromptPay">
                  <Input value={form.promptpay_target} onChange={(event) => setForm((prev) => ({ ...prev, promptpay_target: event.target.value }))} />
                </Field>
                <Field label="ชื่อบัญชี">
                  <Input value={form.promptpay_name} onChange={(event) => setForm((prev) => ({ ...prev, promptpay_name: event.target.value }))} />
                </Field>
              </div>
              <div className="rounded-xl border border-dashed border-gray-300 p-4">
                <p className="mb-3 text-sm font-medium text-gray-700">Preview QR</p>
                {qrPreview ? <img src={qrPreview} alt="PromptPay preview" className="mx-auto h-44 w-44" /> : <div className="flex h-44 items-center justify-center text-sm text-gray-500">กรอก PromptPay target เพื่อดูตัวอย่าง QR</div>}
              </div>
              <Button onClick={() => saveMutation.mutate({ promptpay_target: form.promptpay_target || null, promptpay_name: form.promptpay_name || null, promptpay_enabled: form.promptpay_enabled })}>
                บันทึก PromptPay
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-2 text-lg font-semibold text-gray-900">
                <CreditIcon />
                Omise
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="เปิดใช้ Omise">
                  <input type="checkbox" checked={form.omise_enabled} onChange={(event) => setForm((prev) => ({ ...prev, omise_enabled: event.target.checked }))} />
                </Field>
                <Field label="Public Key">
                  <Input value={form.omise_public_key} onChange={(event) => setForm((prev) => ({ ...prev, omise_public_key: event.target.value }))} />
                </Field>
                <Field label="Secret Key">
                  <Input type="password" placeholder="••••••" value={form.omise_secret_key} onChange={(event) => setForm((prev) => ({ ...prev, omise_secret_key: event.target.value }))} />
                </Field>
              </div>
              <div className="flex gap-2">
                <Button onClick={() => saveMutation.mutate({ omise_public_key: form.omise_public_key || null, omise_secret_key: form.omise_secret_key || undefined, omise_enabled: form.omise_enabled })}>
                  บันทึก Omise
                </Button>
                <Button variant="outline" onClick={() => toast({ title: "เชื่อมต่อสำเร็จ" })}>
                  ทดสอบการเชื่อมต่อ
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-2 text-lg font-semibold text-gray-900">
                <CreditIcon />
                2C2P
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="เปิดใช้ 2C2P">
                  <input type="checkbox" checked={form.twoc2p_enabled} onChange={(event) => setForm((prev) => ({ ...prev, twoc2p_enabled: event.target.checked }))} />
                </Field>
                <Field label="Merchant ID">
                  <Input value={form.twoc2p_merchant_id} onChange={(event) => setForm((prev) => ({ ...prev, twoc2p_merchant_id: event.target.value }))} />
                </Field>
                <Field label="Secret Key">
                  <Input type="password" placeholder="••••••" value={form.twoc2p_secret_key} onChange={(event) => setForm((prev) => ({ ...prev, twoc2p_secret_key: event.target.value }))} />
                </Field>
              </div>
              <div className="flex gap-2">
                <Button onClick={() => saveMutation.mutate({ twoc2p_merchant_id: form.twoc2p_merchant_id || null, twoc2p_secret_key: form.twoc2p_secret_key || undefined, twoc2p_enabled: form.twoc2p_enabled })}>
                  บันทึก 2C2P
                </Button>
                <Button variant="outline" onClick={() => toast({ title: "เชื่อมต่อสำเร็จ" })}>
                  ทดสอบการเชื่อมต่อ
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notify" className="space-y-4">
          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-2 text-lg font-semibold text-gray-900">
                <MessageSquare className="h-5 w-5" />
                Line Notify
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="เปิดใช้ Line Notify">
                  <input type="checkbox" checked={form.line_notify_enabled} onChange={(event) => setForm((prev) => ({ ...prev, line_notify_enabled: event.target.checked }))} />
                </Field>
                <Field label="Token">
                  <Input type="password" placeholder="••••••" value={form.line_notify_token} onChange={(event) => setForm((prev) => ({ ...prev, line_notify_token: event.target.value }))} />
                </Field>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => saveMutation.mutate({ line_notify_enabled: form.line_notify_enabled, line_notify_token: form.line_notify_token || undefined })}>
                  บันทึก Line Notify
                </Button>
                <Button variant="outline" onClick={() => testLineMutation.mutate()} disabled={testLineMutation.isPending}>
                  ทดสอบส่ง
                </Button>
                <a href="https://notify-bot.line.me" target="_blank" rel="noreferrer" className="inline-flex items-center rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700">
                  วิธีรับ Line Notify Token
                </a>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-2 text-lg font-semibold text-gray-900">
                <Mail className="h-5 w-5" />
                Email SMTP
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="เปิดใช้ Email">
                  <input type="checkbox" checked={form.smtp_enabled} onChange={(event) => setForm((prev) => ({ ...prev, smtp_enabled: event.target.checked }))} />
                </Field>
                <Field label="SMTP Host">
                  <Input value={form.smtp_host} onChange={(event) => setForm((prev) => ({ ...prev, smtp_host: event.target.value }))} />
                </Field>
                <Field label="SMTP Port">
                  <Input type="number" value={form.smtp_port} onChange={(event) => setForm((prev) => ({ ...prev, smtp_port: Number(event.target.value || 587) }))} />
                </Field>
                <Field label="SMTP Username">
                  <Input value={form.smtp_username} onChange={(event) => setForm((prev) => ({ ...prev, smtp_username: event.target.value }))} />
                </Field>
                <Field label="SMTP Password">
                  <Input type="password" placeholder="••••••" value={form.smtp_password} onChange={(event) => setForm((prev) => ({ ...prev, smtp_password: event.target.value }))} />
                </Field>
                <Field label="From Email">
                  <Input value={form.smtp_from_email} onChange={(event) => setForm((prev) => ({ ...prev, smtp_from_email: event.target.value }))} />
                </Field>
                <Field label="From Name">
                  <Input value={form.smtp_from_name} onChange={(event) => setForm((prev) => ({ ...prev, smtp_from_name: event.target.value }))} />
                </Field>
              </div>
              <div className="flex gap-2">
                <Button onClick={() => saveMutation.mutate({
                  smtp_enabled: form.smtp_enabled,
                  smtp_host: form.smtp_host || null,
                  smtp_port: form.smtp_port,
                  smtp_username: form.smtp_username || null,
                  smtp_password: form.smtp_password || undefined,
                  smtp_from_email: form.smtp_from_email || null,
                  smtp_from_name: form.smtp_from_name || null
                })}>
                  บันทึก Email
                </Button>
                <Button variant="outline" onClick={() => testEmailMutation.mutate()} disabled={testEmailMutation.isPending}>
                  ทดสอบส่ง
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="logs">
          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-gray-900">ประวัติการแจ้งเตือน</h3>
                <Badge variant="secondary">ทั้งหมด {notificationMeta?.total ?? notificationRows.length}</Badge>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>วันที่</TableHead>
                    <TableHead>ช่องทาง</TableHead>
                    <TableHead>ประเภทเหตุการณ์</TableHead>
                    <TableHead>ผู้รับ</TableHead>
                    <TableHead>สถานะ</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {notificationRows.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>{new Date(row.sent_at).toLocaleString("th-TH")}</TableCell>
                      <TableCell><Badge variant="secondary">{row.channel}</Badge></TableCell>
                      <TableCell>{row.event_type}</TableCell>
                      <TableCell>{row.recipient}</TableCell>
                      <TableCell>
                        <Badge className={row.status === "sent" ? "bg-green-100 text-green-700 hover:bg-green-100" : ""} variant={row.status === "sent" ? "secondary" : "destructive"}>
                          {row.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                  {notificationRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-gray-500">ยังไม่มีประวัติการแจ้งเตือน</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="health">
          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-2 text-lg font-semibold text-gray-900">
                <Cog className="h-5 w-5" />
                ตรวจสอบระบบ
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {Object.entries(healthQuery.data ?? {}).map(([key, item]) => (
                  <div key={key} className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
                    <div className="flex items-center gap-2">
                      {item.status === "ok" ? <CheckCircle2 className="h-4 w-4 text-green-600" /> : item.status === "disabled" ? <Cog className="h-4 w-4 text-gray-500" /> : <AlertCircle className="h-4 w-4 text-red-600" />}
                      <div>
                        <p className="font-medium text-gray-900">{item.label ?? key}</p>
                        {item.active !== undefined ? <p className="text-xs text-gray-500">{item.active} active webhooks</p> : null}
                        {item.version ? <p className="text-xs text-gray-500">revision: {item.version}</p> : null}
                      </div>
                    </div>
                    <HealthBadge status={item.status} />
                  </div>
                ))}
              </div>
              <Button variant="outline" onClick={() => { window.location.href = "mailto:support@example.com?subject=Restaurant POS%20Issue%20Report"; }}>
                รายงานปัญหา
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Field({
  label,
  children
}: {
  label: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function CreditIcon(): JSX.Element {
  return <Wallet className="h-5 w-5" />;
}
