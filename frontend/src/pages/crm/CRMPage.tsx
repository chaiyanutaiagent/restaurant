import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Star } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { crmApi } from "@/lib/crmApi";
import type { Customer, CustomerListItem, CustomerSearchResult, CustomerTag, CustomerTier, LoyaltySettings, PointsTransaction } from "@/types/crm";
import CreateCustomerDialog from "./CreateCustomerDialog";
import CustomerProfileDialog from "./CustomerProfileDialog";
import EarnPointsDialog from "./EarnPointsDialog";
import RedeemPointsDialog from "./RedeemPointsDialog";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(value || 0);
}

function txLabel(type: string): { label: string; className: string } {
  if (type === "earn") return { label: "รับแต้ม", className: "bg-green-100 text-green-700" };
  if (type === "redeem") return { label: "แลกแต้ม", className: "bg-blue-100 text-blue-700" };
  if (type === "expire") return { label: "หมดอายุ", className: "bg-gray-100 text-gray-700" };
  if (type === "adjust") return { label: "ปรับ", className: "bg-yellow-100 text-yellow-700" };
  return { label: "คืนแต้ม", className: "bg-red-100 text-red-700" };
}

export default function CRMPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const canEditPoints = usePermission("system.user.edit");
  const canEditSettings = usePermission("system.company.edit");
  const canCreateCustomer = usePermission("pos.sale.create");

  const [tierFilter, setTierFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [createCustomerOpen, setCreateCustomerOpen] = useState(false);
  const [customerProfileId, setCustomerProfileId] = useState<string | null>(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [loyaltySearch, setLoyaltySearch] = useState("");
  const [earnOpen, setEarnOpen] = useState(false);
  const [redeemOpen, setRedeemOpen] = useState(false);
  const [settingsForm, setSettingsForm] = useState({
    enabled: true,
    require_phone: true,
    earn_rate: 0,
    earn_min_spend: 0,
    redeem_rate: 0,
    redeem_min_points: 0,
    points_expiry_months: 12
  });

  const settingsQuery = useQuery({
    queryKey: ["crm", "settings"],
    queryFn: async () => (await crmApi.getSettings()).data.data as LoyaltySettings
  });
  const tiersQuery = useQuery({
    queryKey: ["crm", "tiers"],
    queryFn: async () => (await crmApi.listTiers()).data.data as CustomerTier[]
  });
  const tagsQuery = useQuery({
    queryKey: ["crm", "tags"],
    queryFn: async () => (await crmApi.listTags()).data.data as CustomerTag[]
  });
  const customersQuery = useQuery({
    queryKey: ["crm", "customers", { tierFilter, tagFilter, statusFilter, search }],
    queryFn: async () =>
      (await crmApi.listCustomers({
        tier_id: tierFilter || undefined,
        tag_id: tagFilter || undefined,
        is_active: statusFilter ? statusFilter === "active" : undefined,
        search: search || undefined,
        page: 1,
        limit: 100
      })).data.data as CustomerListItem[]
  });
  const loyaltySearchQuery = useQuery({
    queryKey: ["crm", "search", loyaltySearch],
    queryFn: async () => (await crmApi.searchCustomers(loyaltySearch, 10)).data.data as CustomerSearchResult[],
    enabled: loyaltySearch.trim().length >= 3
  });
  const selectedCustomerQuery = useQuery({
    queryKey: ["crm", "customer", selectedCustomerId],
    queryFn: async () => (await crmApi.getCustomer(selectedCustomerId!)).data.data as Customer,
    enabled: Boolean(selectedCustomerId)
  });
  const selectedPointsQuery = useQuery({
    queryKey: ["crm", "customer-points", selectedCustomerId],
    queryFn: async () => (await crmApi.getPointsHistory(selectedCustomerId!, { page: 1, limit: 20 })).data.data as PointsTransaction[],
    enabled: Boolean(selectedCustomerId)
  });

  const customers = customersQuery.data ?? [];
  const tiers = tiersQuery.data ?? [];
  const tags = tagsQuery.data ?? [];
  const settings = settingsQuery.data ?? null;
  const selectedCustomer = selectedCustomerQuery.data ?? null;
  const pointsHistory = selectedPointsQuery.data ?? [];

  const selectedCustomerName = selectedCustomer?.display_name
    || [selectedCustomer?.first_name, selectedCustomer?.last_name].filter(Boolean).join(" ")
    || selectedCustomer?.customer_code
    || "-";

  useEffect(() => {
    if (!settingsQuery.data) {
      return;
    }
    setSettingsForm({
      enabled: settingsQuery.data.enabled,
      require_phone: settingsQuery.data.require_phone,
      earn_rate: settingsQuery.data.earn_rate,
      earn_min_spend: settingsQuery.data.earn_min_spend,
      redeem_rate: settingsQuery.data.redeem_rate,
      redeem_min_points: settingsQuery.data.redeem_min_points,
      points_expiry_months: settingsQuery.data.points_expiry_months
    });
  }, [settingsQuery.data]);

  const summary = useMemo(() => {
    const all = customers.length;
    const goldPlus = customers.filter((customer) => customer.tier_name === "Gold" || customer.tier_name === "Platinum").length;
    const newThisMonth = customers.filter((customer) => customer.total_orders === 0).length;
    return { all, goldPlus, newThisMonth };
  }, [customers]);

  const nextTier = useMemo(() => {
    if (!selectedCustomer) return null;
    return tiers.find((tier) => tier.min_lifetime_spend > selectedCustomer.lifetime_spend) ?? null;
  }, [selectedCustomer, tiers]);

  const settingsMutation = useMutation({
    mutationFn: async (payload: Partial<LoyaltySettings>) => crmApi.updateSettings(payload),
    onSuccess: async () => {
      toast({ title: "บันทึกตั้งค่าระบบแต้มแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["crm", "settings"] });
    },
    onError: (error: Error) => {
      toast({ title: "บันทึกไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  const adjustPointsMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCustomer) throw new Error("ไม่พบสมาชิก");
      const points = Number(window.prompt("จำนวนแต้ม (+/-)") || "0");
      const note = window.prompt("หมายเหตุ") || "Manual adjustment";
      return crmApi.adjustPoints({ customer_id: selectedCustomer.id, points, note });
    },
    onSuccess: async () => {
      toast({ title: "ปรับแต้มแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["crm"] });
    },
    onError: (error: Error) => {
      toast({ title: "ปรับแต้มไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <div className="space-y-6">
      <PageHeader title="ลูกค้า" subtitle="CRM + Loyalty" />
      <Tabs defaultValue="customers">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="customers">สมาชิกทั้งหมด</TabsTrigger>
          <TabsTrigger value="loyalty">แต้มสะสม</TabsTrigger>
          <TabsTrigger value="settings">ตั้งค่าระบบแต้ม</TabsTrigger>
        </TabsList>

        <TabsContent value="customers">
          <Card>
            <CardContent className="space-y-4 p-4">
              <div className="flex flex-wrap gap-2">
                <button type="button" className={`rounded-full px-3 py-2 text-sm ${tierFilter === "" ? "bg-slate-900 text-white" : "border"}`} onClick={() => setTierFilter("")}>ทุกระดับ</button>
                {tiers.map((tier) => (
                  <button key={tier.id} type="button" className={`rounded-full border px-3 py-2 text-sm ${tierFilter === tier.id ? "text-white" : ""}`} style={{ backgroundColor: tierFilter === tier.id ? tier.color ?? "#334155" : "white", borderColor: tier.color ?? "#cbd5e1", color: tierFilter === tier.id ? "white" : tier.color ?? "#334155" }} onClick={() => setTierFilter(tier.id)}>
                    {tier.name}
                  </button>
                ))}
                <select className="h-10 rounded-md border border-gray-300 px-3" value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
                  <option value="">ทุก Tag</option>
                  {tags.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
                </select>
                <select className="h-10 rounded-md border border-gray-300 px-3" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">ทุกสถานะ</option>
                  <option value="active">active</option>
                  <option value="inactive">inactive</option>
                </select>
                <Input className="max-w-sm" placeholder="ค้นหาชื่อ / เบอร์ / รหัส" value={search} onChange={(event) => setSearch(event.target.value)} />
                {canCreateCustomer ? <Button className="ml-auto" onClick={() => setCreateCustomerOpen(true)}><Plus className="h-4 w-4" />เพิ่มสมาชิก</Button> : null}
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-lg border p-4">สมาชิกทั้งหมด: {summary.all} คน</div>
                <div className="rounded-lg border p-4">ระดับ Gold+: {summary.goldPlus}</div>
                <div className="rounded-lg border p-4">สมาชิกใหม่เดือนนี้: {summary.newThisMonth}</div>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>รหัส</TableHead>
                    <TableHead>ชื่อ-นามสกุล</TableHead>
                    <TableHead>เบอร์โทร</TableHead>
                    <TableHead>Tier</TableHead>
                    <TableHead>แต้มคงเหลือ</TableHead>
                    <TableHead>ยอดซื้อสะสม</TableHead>
                    <TableHead>จำนวนออเดอร์</TableHead>
                    <TableHead>ซื้อล่าสุด</TableHead>
                    <TableHead>สถานะ</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {customers.map((customer) => (
                    <TableRow key={customer.id}>
                      <TableCell className="font-mono">{customer.customer_code}</TableCell>
                      <TableCell>{customer.display_name || [customer.first_name, customer.last_name].filter(Boolean).join(" ") || "-"}</TableCell>
                      <TableCell>{customer.phone || "-"}</TableCell>
                      <TableCell>{customer.tier_name || "-"}</TableCell>
                      <TableCell><span className="inline-flex items-center gap-1"><Star className="h-4 w-4 text-amber-400" />{customer.points_balance}</span></TableCell>
                      <TableCell>{formatCurrency(customer.lifetime_spend)}</TableCell>
                      <TableCell>{customer.total_orders}</TableCell>
                      <TableCell>{customer.last_purchase_at ? new Date(customer.last_purchase_at).toLocaleDateString("th-TH") : "ยังไม่เคยซื้อ"}</TableCell>
                      <TableCell>{customer.is_active ? "active" : "inactive"}</TableCell>
                      <TableCell><Button variant="outline" size="sm" onClick={() => setCustomerProfileId(customer.id)}>ดูโปรไฟล์</Button></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="loyalty">
          <div className="grid gap-6 lg:grid-cols-[360px,1fr]">
            <Card>
              <CardContent className="space-y-4 p-4">
                <Input placeholder="ค้นหาสมาชิก (เบอร์โทร/ชื่อ)" value={loyaltySearch} onChange={(event) => setLoyaltySearch(event.target.value)} />
                <div className="space-y-2">
                  {(loyaltySearchQuery.data ?? []).map((customer) => (
                    <button key={customer.id} type="button" className="w-full rounded-lg border p-3 text-left" onClick={() => setSelectedCustomerId(customer.id)}>
                      <div className="font-medium">{customer.display_name || customer.customer_code}</div>
                      <div className="text-xs text-gray-500">{customer.phone || "-"} • {customer.tier_name || "-"}</div>
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-4 p-4">
                {selectedCustomer ? (
                  <>
                    <div className="rounded-xl border bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="text-xl font-semibold">{selectedCustomerName}</div>
                          <div className="mt-1 inline-flex rounded-full px-3 py-1 text-sm font-medium" style={{ backgroundColor: `${selectedCustomer.tier?.color ?? "#cbd5e1"}22`, color: selectedCustomer.tier?.color ?? "#334155" }}>
                            {selectedCustomer.tier?.name_th ?? selectedCustomer.tier?.name ?? "No Tier"}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-3xl font-bold text-amber-500">{selectedCustomer.points_balance} ⭐</div>
                          <div className="text-sm text-slate-500">แต้มคงเหลือ</div>
                        </div>
                      </div>
                      <div className="mt-4 grid gap-3 md:grid-cols-3">
                        <div>ยอดซื้อสะสม: {formatCurrency(selectedCustomer.lifetime_spend)}</div>
                        <div>ออเดอร์รวม: {selectedCustomer.total_orders} ครั้ง</div>
                        <div>{nextTier ? `อีก ${formatCurrency(nextTier.min_lifetime_spend - selectedCustomer.lifetime_spend)} ถึงระดับ ${nextTier.name}` : "ถึงระดับสูงสุดแล้ว"}</div>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button onClick={() => setEarnOpen(true)}>ให้แต้ม</Button>
                        <Button variant="outline" onClick={() => setRedeemOpen(true)}>แลกแต้ม</Button>
                        {canEditPoints ? <Button variant="secondary" onClick={() => adjustPointsMutation.mutate()}>ปรับแต้มแบบ Manual</Button> : null}
                      </div>
                    </div>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>วันที่</TableHead>
                          <TableHead>ประเภท</TableHead>
                          <TableHead>แต้ม</TableHead>
                          <TableHead>ยอดซื้อ</TableHead>
                          <TableHead>คงเหลือ</TableHead>
                          <TableHead>หมายเหตุ</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {pointsHistory.map((tx) => {
                          const meta = txLabel(tx.transaction_type);
                          return (
                            <TableRow key={tx.id}>
                              <TableCell>{new Date(tx.created_at).toLocaleString("th-TH")}</TableCell>
                              <TableCell><span className={`rounded-full px-2 py-1 text-xs font-medium ${meta.className}`}>{meta.label}</span></TableCell>
                              <TableCell>{tx.points}</TableCell>
                              <TableCell>{tx.spend_amount ?? tx.redeem_amount ?? "-"}</TableCell>
                              <TableCell>{tx.balance_after}</TableCell>
                              <TableCell>{tx.note || "-"}</TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </>
                ) : (
                  <div className="py-12 text-center text-slate-400">ค้นหาและเลือกสมาชิกเพื่อดูข้อมูลแต้ม</div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="settings">
          <div className="grid gap-6 lg:grid-cols-[1.2fr,1fr]">
            <Card>
              <CardContent className="space-y-4 p-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2"><label className="text-sm font-medium">เปิดใช้ระบบแต้ม</label><select className="h-10 w-full rounded-md border border-gray-300 px-3" value={String(settingsForm.enabled)} onChange={(event) => setSettingsForm((prev) => ({ ...prev, enabled: event.target.value === "true" }))} disabled={!canEditSettings}><option value="true">เปิด</option><option value="false">ปิด</option></select></div>
                  <div className="space-y-2"><label className="text-sm font-medium">บังคับใส่เบอร์โทร</label><select className="h-10 w-full rounded-md border border-gray-300 px-3" value={String(settingsForm.require_phone)} onChange={(event) => setSettingsForm((prev) => ({ ...prev, require_phone: event.target.value === "true" }))} disabled={!canEditSettings}><option value="true">ใช่</option><option value="false">ไม่ใช่</option></select></div>
                  <div className="space-y-2"><label className="text-sm font-medium">อัตราสะสมแต้ม</label><Input type="number" value={settingsForm.earn_rate} onChange={(event) => setSettingsForm((prev) => ({ ...prev, earn_rate: Number(event.target.value) }))} disabled={!canEditSettings} /></div>
                  <div className="space-y-2"><label className="text-sm font-medium">ยอดขั้นต่ำในการรับแต้ม</label><Input type="number" value={settingsForm.earn_min_spend} onChange={(event) => setSettingsForm((prev) => ({ ...prev, earn_min_spend: Number(event.target.value) }))} disabled={!canEditSettings} /></div>
                  <div className="space-y-2"><label className="text-sm font-medium">อัตราแลกแต้ม</label><Input type="number" value={settingsForm.redeem_rate} onChange={(event) => setSettingsForm((prev) => ({ ...prev, redeem_rate: Number(event.target.value) }))} disabled={!canEditSettings} /></div>
                  <div className="space-y-2"><label className="text-sm font-medium">แต้มขั้นต่ำในการแลก</label><Input type="number" value={settingsForm.redeem_min_points} onChange={(event) => setSettingsForm((prev) => ({ ...prev, redeem_min_points: Number(event.target.value) }))} disabled={!canEditSettings} /></div>
                  <div className="space-y-2"><label className="text-sm font-medium">อายุแต้ม (เดือน)</label><Input type="number" value={settingsForm.points_expiry_months} onChange={(event) => setSettingsForm((prev) => ({ ...prev, points_expiry_months: Number(event.target.value) }))} disabled={!canEditSettings} /></div>
                </div>
                <Button onClick={() => settingsMutation.mutate(settingsForm)} disabled={!canEditSettings || settingsMutation.isPending}>Save</Button>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tier</TableHead>
                      <TableHead>ยอดซื้อสะสมขั้นต่ำ</TableHead>
                      <TableHead>ตัวคูณแต้ม</TableHead>
                      <TableHead>สีสัญลักษณ์</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tiers.map((tier) => (
                      <TableRow key={tier.id}>
                        <TableCell>{tier.name}</TableCell>
                        <TableCell>{formatCurrency(tier.min_lifetime_spend)}</TableCell>
                        <TableCell>{tier.points_multiplier}x</TableCell>
                        <TableCell><span className="inline-block h-4 w-4 rounded-full" style={{ backgroundColor: tier.color ?? "#cbd5e1" }} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      <CreateCustomerDialog open={createCustomerOpen} onOpenChange={setCreateCustomerOpen} requirePhone={settings?.require_phone ?? true} />
      <CustomerProfileDialog open={Boolean(customerProfileId)} onOpenChange={(isOpen) => !isOpen && setCustomerProfileId(null)} customerId={customerProfileId} tags={tags} />
      <EarnPointsDialog open={earnOpen} onOpenChange={setEarnOpen} customer={selectedCustomer} settings={settings} />
      <RedeemPointsDialog open={redeemOpen} onOpenChange={setRedeemOpen} customer={selectedCustomer} settings={settings} />
    </div>
  );
}
