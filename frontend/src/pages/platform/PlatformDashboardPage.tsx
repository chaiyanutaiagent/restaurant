import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  Cpu,
  Database,
  LayoutDashboard,
  MapPin,
  RefreshCw,
  ShoppingBag,
  ShoppingCart,
  Store,
  Users,
  UtensilsCrossed,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";
import type { PlatformAuditEvent } from "@/types/platform";

const numberFormatter = new Intl.NumberFormat("th-TH");

const featureMeta: Record<string, { label: string; description: string; icon: typeof Store; color: string }> = {
  restaurant: {
    label: "Restaurant",
    description: "ร้านอาหาร มีโต๊ะและสั่งกลับบ้าน",
    icon: UtensilsCrossed,
    color: "bg-orange-400 text-slate-950",
  },
  takeaway: {
    label: "Takeaway",
    description: "ขายกลับบ้านและเก็บเงินก่อน",
    icon: ShoppingBag,
    color: "bg-violet-400 text-slate-950",
  },
  retail_pos: {
    label: "Retail POS",
    description: "ขายสินค้าทั่วไปและสแกนบาร์โค้ด",
    icon: ShoppingCart,
    color: "bg-sky-400 text-slate-950",
  },
};

const actionLabels: Record<string, string> = {
  "platform.company.create": "เปิด Company ใหม่",
  "platform.company.controls.update": "แก้ไข Plan หรือระบบที่เปิดใช้",
  "platform.company.suspend": "ระงับ Company",
  "platform.company.reactivate": "เปิด Company กลับมาใช้งาน",
  "platform.company.export": "ดาวน์โหลด Tenant export",
  "platform.operator.login": "Platform Owner เข้าสู่ระบบ",
  "platform.operator.logout": "Platform Owner ออกจากระบบ",
  "platform.operator.logout_all": "ออกจาก Platform ทุกเครื่อง",
  "platform.operator.session.revoke": "เพิกถอน Platform session",
  "platform.operator.mfa.enable": "เปิด Platform MFA",
  "platform.operator.mfa.disable": "ปิด Platform MFA",
  "platform.operator.mfa.recovery_codes.rotate": "สร้าง MFA recovery codes ใหม่",
  "platform.operator.password.change": "เปลี่ยนรหัสผ่าน Platform Owner",
  "platform.operator.password.break_glass_reset": "Break-glass reset Platform Owner",
  "platform.usage.snapshot.capture": "บันทึก Tenant usage snapshot",
  "platform.operations.snapshot.capture": "บันทึก Platform runtime snapshot",
  "platform.operations.evidence.import": "นำเข้า Operations evidence",
};

const attentionLabels: Record<string, string> = {
  suspended: "ถูกระงับ",
  onboarding_pending: "ตั้งค่ายังไม่ครบ",
  unpaired_devices: "มีอุปกรณ์รอจับคู่",
  planned_feature_configured: "ตั้งค่า Feature ที่ยัง Planned",
  stale_activity: "ไม่มีกิจกรรมเกิน 14 วัน",
  "limit_exceeded:brands": "แบรนด์เกิน Limit",
  "limit_exceeded:branches": "สาขาเกิน Limit",
  "limit_exceeded:users": "บัญชีผู้ใช้เกิน Limit",
  "limit_exceeded:devices": "อุปกรณ์เกิน Limit",
};

function attentionLabel(code: string): string {
  return attentionLabels[code] ?? code;
}

function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

function eventLabel(event: PlatformAuditEvent): string {
  return actionLabels[event.action] ?? event.action;
}

export default function PlatformDashboardPage(): JSX.Element {
  const queryClient = useQueryClient();
  const dashboard = useQuery({
    queryKey: ["platform", "dashboard"],
    queryFn: async () => (await platformApi.dashboard()).data.data,
    refetchInterval: 60_000,
  });
  const captureSnapshots = useMutation({
    mutationFn: () => platformApi.captureUsageSnapshots(),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["platform", "dashboard"] }),
  });

  if (dashboard.isLoading) return <DashboardSkeleton />;

  if (dashboard.error || !dashboard.data) {
    return (
      <div className="rounded-2xl border border-red-900 bg-red-950/40 p-6">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-6 w-6 text-red-300" />
          <div>
            <h2 className="text-lg font-semibold text-red-100">โหลดภาพรวม Platform ไม่สำเร็จ</h2>
            <p className="mt-1 text-sm text-red-200/80">{platformErrorMessage(dashboard.error)}</p>
            <Button className="mt-4" variant="outline" onClick={() => void dashboard.refetch()}>
              <RefreshCw className="h-4 w-4" /> ลองใหม่
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const data = dashboard.data;
  const readinessPercent = data.onboarding.total_active_companies
    ? Math.round((data.onboarding.ready_companies / data.onboarding.total_active_companies) * 100)
    : 0;
  const attentionCount = data.attention_summary.companies ?? 0;
  const unpairedDevices = Math.max(data.totals.devices - data.totals.paired_devices, 0);
  const totalPlanCompanies = Object.values(data.plan_usage).reduce((sum, count) => sum + count, 0);
  const productStatusLabel = (status: "pilot" | "planned") => status === "pilot" ? "PILOT" : "PLANNED";

  return (
    <div className="space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-emerald-300">Platform overview</p>
          <h2 className="mt-1 text-3xl font-bold tracking-tight">ภาพรวมระบบ</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
            สถานะลูกค้า ความพร้อมเปิดใช้งาน และทรัพยากรสำคัญของ Platform ในหน้าเดียว
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs text-slate-500">
            อัปเดต {new Date(data.generated_at).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" })} น.
          </span>
          <Button asChild className="bg-emerald-400 text-slate-950 hover:bg-emerald-300">
            <Link to="/platform/companies">
              จัดการบริษัทลูกค้า <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button variant="outline" onClick={() => captureSnapshots.mutate()} disabled={captureSnapshots.isPending}>
            <Database className="h-4 w-4" />
            {captureSnapshots.isPending ? "กำลังบันทึก..." : "บันทึก Usage วันนี้"}
          </Button>
        </div>
      </header>

      {captureSnapshots.error ? <p className="rounded-xl border border-red-900 bg-red-950/40 p-3 text-sm text-red-200">{platformErrorMessage(captureSnapshots.error)}</p> : null}
      {captureSnapshots.isSuccess ? <p className="rounded-xl border border-emerald-900 bg-emerald-950/30 p-3 text-sm text-emerald-200">บันทึก aggregate usage snapshot วันนี้แล้ว โดยไม่มีข้อมูลออเดอร์หรือลูกค้า</p> : null}

      <section className="rounded-2xl border border-amber-800/70 bg-amber-950/30 px-5 py-4" aria-label="สถานะการเปิดระบบ">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
          <div>
            <p className="font-semibold text-amber-100">Restaurant อยู่ในสถานะ Pilot — รอ Physical UAT</p>
            <p className="mt-1 text-sm leading-6 text-amber-200/75">
              ตัวเลขความพร้อมด้านล่างหมายถึงการตั้งค่าพื้นฐานของ Tenant ไม่ใช่การอนุมัติ Production;
              Takeaway และ Retail POS ยังเป็นแผนงานและยังไม่เปิดใช้งาน
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="ตัวเลขสำคัญ">
        <MetricCard
          label="บริษัทลูกค้าทั้งหมด"
          value={data.totals.companies}
          hint={`เพิ่มใหม่ล่าสุด ${data.recent_companies[0]?.name ?? "ยังไม่มีข้อมูล"}`}
          icon={<Building2 className="h-5 w-5" />}
          tone="emerald"
        />
        <MetricCard
          label="กำลังใช้งาน"
          value={data.totals.active_companies}
          hint={`${data.totals.suspended_companies} บริษัทถูกระงับ`}
          icon={<Activity className="h-5 w-5" />}
          tone="sky"
        />
        <MetricCard
          label="ตั้งค่าพื้นฐานพร้อม"
          value={data.onboarding.ready_companies}
          hint={`${readinessPercent}% ของบริษัทที่ Active`}
          icon={<CheckCircle2 className="h-5 w-5" />}
          tone="violet"
        />
        <MetricCard
          label="ต้องติดตาม"
          value={attentionCount}
          hint={`${data.onboarding.pending_companies} onboarding ค้าง · ${data.totals.suspended_companies} ระงับ`}
          icon={<AlertTriangle className="h-5 w-5" />}
          tone={attentionCount > 0 ? "amber" : "slate"}
        />
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-100">ความพร้อมของลูกค้า</p>
              <p className="mt-1 text-xs text-slate-400">
                Restaurant → Company → Brand → Branch → Menu → Staff; Payment และ Device จะนับเมื่อมีการตั้งค่า
              </p>
            </div>
            <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-sm font-semibold text-emerald-300">
              {readinessPercent}% ตั้งค่าพร้อม
            </span>
          </div>
          <div className="mt-5 h-3 overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-emerald-400 transition-all" style={{ width: `${readinessPercent}%` }} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <SummaryBlock label="ตั้งค่าพร้อม" value={data.onboarding.ready_companies} accent="text-emerald-300" />
            <SummaryBlock label="กำลังตั้งค่า" value={data.onboarding.pending_companies} accent="text-amber-300" />
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm font-semibold text-slate-100">Plan ที่กำลังใช้งาน</p>
          <div className="mt-4 space-y-3">
            {Object.entries(data.plan_usage).length ? Object.entries(data.plan_usage).map(([plan, count]) => {
              const percent = totalPlanCompanies ? Math.round((count / totalPlanCompanies) * 100) : 0;
              return (
                <div key={plan}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium capitalize text-slate-200">{plan}</span>
                    <span className="text-slate-400">{formatNumber(count)} บริษัท</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                    <div className="h-full rounded-full bg-sky-400" style={{ width: `${percent}%` }} />
                  </div>
                </div>
              );
            }) : <p className="text-sm text-slate-500">ยังไม่มีข้อมูล Plan</p>}
          </div>
        </div>
      </section>

      <section>
        <div className="mb-3">
          <h3 className="text-lg font-semibold">ทรัพยากรในระบบ</h3>
          <p className="mt-1 text-sm text-slate-400">นับเฉพาะรายการที่ยัง Active</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <ResourceCard icon={<Store className="h-5 w-5" />} label="แบรนด์" value={data.totals.brands} />
          <ResourceCard icon={<MapPin className="h-5 w-5" />} label="สาขา" value={data.totals.branches} />
          <ResourceCard icon={<Users className="h-5 w-5" />} label="บัญชีผู้ใช้ที่เปิดใช้งาน" value={data.totals.enabled_user_accounts} />
          <ResourceCard
            icon={<Cpu className="h-5 w-5" />}
            label="อุปกรณ์"
            value={data.totals.devices}
            detail={`${formatNumber(data.totals.paired_devices)} paired · ${formatNumber(unpairedDevices)} รอจับคู่`}
          />
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="font-semibold">สาเหตุที่ต้องติดตาม</h3>
        <p className="mt-1 text-xs text-slate-400">กฎจาก aggregate usage และสถานะการตั้งค่า ไม่อ่านรายละเอียดออเดอร์หรือลูกค้า</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {Object.entries(data.attention_summary).filter(([key, count]) => key !== "companies" && count > 0).length ? (
            Object.entries(data.attention_summary)
              .filter(([key, count]) => key !== "companies" && count > 0)
              .map(([key, count]) => (
                <span key={key} className="rounded-full bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-300">
                  {attentionLabel(key)} · {formatNumber(count)}
                </span>
              ))
          ) : <p className="text-sm text-emerald-300">ยังไม่มี Tenant ที่เข้าเงื่อนไขต้องติดตาม</p>}
        </div>
      </section>

      <section>
        <div className="mb-3">
          <h3 className="text-lg font-semibold">ระบบที่เปิดให้ลูกค้า</h3>
          <p className="mt-1 text-sm text-slate-400">จำนวน Company ที่ Active และตั้งค่า Feature ไว้ แยกจากสถานะการเปิดผลิตภัณฑ์</p>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {Object.entries(featureMeta).map(([key, meta]) => {
            const Icon = meta.icon;
            const enabled = data.feature_usage[key] ?? 0;
            const releaseStatus = data.product_status[key] ?? "planned";
            return (
              <article key={key} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className={`rounded-xl p-2.5 ${meta.color}`}><Icon className="h-5 w-5" /></div>
                  <div className="text-right">
                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold tracking-wide ${releaseStatus === "pilot" ? "bg-amber-400/15 text-amber-300" : "bg-slate-700 text-slate-300"}`}>
                      {productStatusLabel(releaseStatus)}
                    </span>
                    <p className="mt-3 text-3xl font-bold text-white">{formatNumber(enabled)}</p>
                  </div>
                </div>
                <h4 className="mt-5 font-semibold text-slate-100">{meta.label}</h4>
                <p className="mt-1 text-sm leading-5 text-slate-400">{meta.description}</p>
                <p className="mt-3 text-xs font-medium text-slate-500">
                  {releaseStatus === "pilot" ? "เปิดเฉพาะ Pilot และยังไม่ผ่าน Production sign-off" : "ยังไม่เปิดใช้งาน — อยู่ในแผนงานอนาคต"}
                </p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
            <div>
              <h3 className="font-semibold">บริษัทล่าสุด</h3>
              <p className="mt-1 text-xs text-slate-400">สถานะและความคืบหน้า onboarding</p>
            </div>
            <Link to="/platform/companies" className="text-sm font-semibold text-emerald-300 hover:text-emerald-200">ดูทั้งหมด</Link>
          </div>
          <div className="divide-y divide-slate-800">
            {data.recent_companies.length ? data.recent_companies.map((company) => {
              const progress = Math.round((company.completed_steps / company.total_steps) * 100);
              return (
                <Link key={company.id} to={`/platform/companies/${company.id}`} className="block px-5 py-4 transition hover:bg-slate-800/60">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate font-semibold text-slate-100">{company.name}</p>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${company.is_active ? "bg-emerald-400/15 text-emerald-300" : "bg-red-400/15 text-red-300"}`}>
                          {company.is_active ? "ACTIVE" : "SUSPENDED"}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">Plan {company.plan_code} · กิจกรรมล่าสุด {company.last_activity_at ? new Date(company.last_activity_at).toLocaleString("th-TH") : "ยังไม่มี"}</p>
                      {company.attention_codes.length ? (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {company.attention_codes.map((code) => <span key={code} className="rounded-full bg-amber-400/10 px-2 py-0.5 text-[10px] text-amber-300">{attentionLabel(code)}</span>)}
                        </div>
                      ) : null}
                    </div>
                    <div className="shrink-0 text-right">
                      <p className={`text-sm font-semibold ${company.onboarding_complete ? "text-emerald-300" : "text-amber-300"}`}>{progress}%</p>
                      <p className="mt-1 text-[11px] text-slate-500">{company.completed_steps}/{company.total_steps} ขั้นตอน</p>
                    </div>
                  </div>
                </Link>
              );
            }) : <p className="px-5 py-10 text-center text-sm text-slate-500">ยังไม่มีบริษัทลูกค้า</p>}
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
            <div>
              <h3 className="font-semibold">กิจกรรมล่าสุด</h3>
              <p className="mt-1 text-xs text-slate-400">การจัดการระดับ Platform</p>
            </div>
            <Link to="/platform/audit" className="text-sm font-semibold text-emerald-300 hover:text-emerald-200">Audit Log</Link>
          </div>
          <div className="divide-y divide-slate-800">
            {data.recent_events.length ? data.recent_events.map((event) => (
              <article key={event.id} className="flex gap-3 px-5 py-4">
                <div className="mt-0.5 rounded-lg bg-slate-800 p-2 text-emerald-300"><Activity className="h-4 w-4" /></div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-200">{eventLabel(event)}</p>
                  <p className="mt-1 truncate text-xs text-slate-500">{event.company_id ? `Company ${event.company_id.slice(0, 8)}` : "Platform"} · {new Date(event.created_at).toLocaleString("th-TH")}</p>
                </div>
              </article>
            )) : <p className="px-5 py-10 text-center text-sm text-slate-500">ยังไม่มีกิจกรรม</p>}
          </div>
        </div>
      </section>
    </div>
  );
}

function MetricCard({ label, value, hint, icon, tone }: { label: string; value: number; hint: string; icon: JSX.Element; tone: "emerald" | "sky" | "violet" | "amber" | "slate" }): JSX.Element {
  const tones = {
    emerald: "bg-emerald-400/15 text-emerald-300",
    sky: "bg-sky-400/15 text-sky-300",
    violet: "bg-violet-400/15 text-violet-300",
    amber: "bg-amber-400/15 text-amber-300",
    slate: "bg-slate-700 text-slate-300",
  };
  return (
    <article className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-slate-400">{label}</p>
        <div className={`rounded-lg p-2 ${tones[tone]}`}>{icon}</div>
      </div>
      <p className="mt-4 text-4xl font-bold tracking-tight text-white">{formatNumber(value)}</p>
      <p className="mt-2 truncate text-xs text-slate-500">{hint}</p>
    </article>
  );
}

function ResourceCard({ icon, label, value, detail }: { icon: JSX.Element; label: string; value: number; detail?: string }): JSX.Element {
  return (
    <article className="flex items-center gap-4 rounded-xl border border-slate-800 bg-slate-900 px-4 py-4">
      <div className="rounded-xl bg-slate-800 p-3 text-sky-300">{icon}</div>
      <div>
        <p className="text-2xl font-bold text-white">{formatNumber(value)}</p>
        <p className="text-sm text-slate-400">{label}</p>
        {detail ? <p className="mt-1 text-[11px] text-slate-500">{detail}</p> : null}
      </div>
    </article>
  );
}

function SummaryBlock({ label, value, accent }: { label: string; value: number; accent: string }): JSX.Element {
  return <div className="rounded-xl bg-slate-950 px-4 py-3"><p className={`text-2xl font-bold ${accent}`}>{formatNumber(value)}</p><p className="mt-1 text-xs text-slate-500">{label}</p></div>;
}

function DashboardSkeleton(): JSX.Element {
  return (
    <div className="space-y-7" aria-label="กำลังโหลดภาพรวม Platform">
      <div className="h-20 animate-pulse rounded-2xl bg-slate-900" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => <div key={item} className="h-36 animate-pulse rounded-2xl bg-slate-900" />)}
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <div className="h-64 animate-pulse rounded-2xl bg-slate-900" />
        <div className="h-64 animate-pulse rounded-2xl bg-slate-900" />
      </div>
      <div className="flex items-center gap-3 text-sm text-slate-500"><LayoutDashboard className="h-4 w-4" />กำลังรวบรวมตัวเลขสำคัญ...</div>
    </div>
  );
}
