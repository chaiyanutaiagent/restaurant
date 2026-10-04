import { CheckCircle2, Clock3, LockKeyhole, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { SystemState } from "@/components/ui/system-state";
import { cn } from "@/lib/utils";
import type { SupplyChainRelease } from "@/types/supplyChainRelease";

type SupplyChainReleasePanelProps = {
  release: SupplyChainRelease;
  online: boolean;
  title: string;
  description: string;
  testId: string;
  accent?: "emerald" | "cyan";
};

const checkStyle = {
  pass: "border-emerald-200 bg-emerald-50 text-emerald-900",
  pending: "border-amber-200 bg-amber-50 text-amber-900",
  hold: "border-slate-200 bg-slate-50 text-slate-700",
};

const checkLabel = { pass: "พร้อมอ่าน", pending: "รอข้อมูล", hold: "HOLD" };

export default function SupplyChainReleasePanel({
  release,
  online,
  title,
  description,
  testId,
  accent = "emerald",
}: SupplyChainReleasePanelProps): JSX.Element {
  const generatedAt = Date.parse(release.generated_at);
  const stale = Number.isFinite(generatedAt)
    && Date.now() - generatedAt > release.stale_after_seconds * 1000;
  const accentClass = accent === "cyan" ? "text-cyan-800" : "text-emerald-800";

  return (
    <section className="space-y-4" data-testid={testId}>
      {!online ? (
        <SystemState kind="offline" compact title="ออฟไลน์ — ปิดคำสั่ง Supply Chain" description="ข้อมูลล่าสุดยังดูได้ แต่ห้ามใช้ตัดสินใจตัดสต๊อก ผลิต หรือส่งสินค้า" />
      ) : stale ? (
        <SystemState kind="stale" compact updatedAt={new Date(generatedAt).toLocaleString("th-TH")} description="โหลดข้อมูลใหม่ก่อนใช้ตรวจนับหรือวางแผนงาน" />
      ) : null}
      <div className="rounded-2xl border border-amber-300 bg-amber-50 p-5 text-amber-950 shadow-sm">
        <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
          <div className="flex gap-3">
            <ShieldCheck className="mt-0.5 h-6 w-6 shrink-0" />
            <div>
              <h2 className="font-black">{title}</h2>
              <p className="mt-1 text-sm leading-6">{description}</p>
            </div>
          </div>
          <Badge className="border-amber-300 bg-white text-amber-900">{release.release_stage === "read_only" ? "READ ONLY" : "UAT CANARY"}</Badge>
        </div>
        <p className="mt-3 flex items-center gap-2 text-xs text-amber-800"><Clock3 className="h-3.5 w-3.5" />Server update {new Date(generatedAt).toLocaleString("th-TH")}</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {release.checks.map((check) => (
          <article key={check.key} className={cn("rounded-xl border p-4", checkStyle[check.state])} data-release-check={check.key}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                {check.state === "pass" ? <CheckCircle2 className="h-4 w-4" /> : <LockKeyhole className="h-4 w-4" />}
                <h3 className="text-sm font-black">{check.label}</h3>
              </div>
              <span className="text-[10px] font-black uppercase tracking-wider">{checkLabel[check.state]}</span>
            </div>
            <p className="mt-2 text-xs leading-5 opacity-80">{check.detail}</p>
          </article>
        ))}
      </div>
      <p className={cn("text-xs font-bold", accentClass)}>ยังปิดคำสั่งจริง {release.hard_holds.length} เงื่อนไข จนกว่าจะมีหลักฐานและผู้รับผิดชอบอนุมัติครบ</p>
    </section>
  );
}
