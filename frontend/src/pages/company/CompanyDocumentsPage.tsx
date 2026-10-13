import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileText, RefreshCw, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";
import DocumentRegister from "@/components/company/DocumentRegister";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { DOCUMENT_GROUPS, filterBusinessDocuments, visibleBusinessDocuments, type DocumentGroup } from "@/config/businessDocuments";
import { companyFoundationApi } from "@/lib/api";
import { companyRequestState } from "@/lib/companyPresentation";
import { useAuthStore } from "@/stores/auth.store";

export default function CompanyDocumentsPage(): JSX.Element {
  const companyId = useAuthStore((state) => state.companyId);
  const branchId = useAuthStore((state) => state.branchId);
  const stationKey = useAuthStore((state) => state.stationKey);
  const permissions = useAuthStore((state) => state.permissions);
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState<DocumentGroup | "all">("all");
  const [online, setOnline] = useState(() => navigator.onLine);
  const entries = visibleBusinessDocuments(permissions);
  const context = useQuery({
    queryKey: ["company-document-context", companyId, branchId, stationKey],
    queryFn: async () => (await companyFoundationApi.context()).data.data,
    enabled: Boolean(companyId) && entries.length > 0,
    retry: false,
  });

  useEffect(() => {
    const update = (): void => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  if (!companyId || entries.length === 0) return <CompanyStatePanel kind="permission_denied" />;
  if (context.isLoading) return <div data-testid="documents-loading"><Skeleton className="mb-4 h-10 w-64" /><Skeleton className="h-80 w-full rounded-2xl" /></div>;
  if (context.error || !context.data) return <CompanyStatePanel kind={!online ? "offline" : companyRequestState(context.error)} onRetry={() => void context.refetch()} />;
  if (context.data.company.id !== companyId || (branchId && context.data.branch?.id !== branchId)) {
    return <CompanyStatePanel kind="permission_denied" title="บริบทเอกสารไม่ตรงกับบัญชีที่ใช้งาน" description="กรุณาเลือกบริษัทและสาขาใหม่ก่อนเปิดเอกสาร" />;
  }

  const filtered = filterBusinessDocuments(entries, search, group);
  const availableGroups = Object.entries(DOCUMENT_GROUPS).filter(([key]) => entries.some((entry) => entry.group === key));

  return (
    <div data-testid="company-documents">
      <PageHeader
        title="ศูนย์เอกสาร"
        subtitle={`${context.data.company.name} · ${context.data.brand?.name ?? "ระดับบริษัท"} · ${context.data.branch?.name ?? "ตามขอบเขตสิทธิ์ของคุณ"}`}
        actions={<Button variant="outline" className="min-h-11" disabled={!online || context.isFetching} onClick={() => void context.refetch()}><RefreshCw className="mr-2 h-4 w-4" />ตรวจบริบทอีกครั้ง</Button>}
      />
      <div className="mb-5 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm leading-6 text-blue-950">
        รวมทางเข้า ทะเบียน ประวัติ และหลักฐานเอกสารใหม่จากระบบเดิม เอกสารเก่าไม่สร้างหลักฐานย้อนหลัง ตัวเลขประเภทด้านล่างไม่ใช่จำนวนธุรกรรม
        การเปิดหน้านี้ไม่สร้างรายการบัญชี ไม่รับชำระเงิน และไม่ออกเอกสารภาษี
      </div>
      {!online ? <div className="mb-5" data-testid="documents-offline"><CompanyStatePanel kind="offline" compact description="ดูประเภทเอกสารได้ แต่ต้องเชื่อมต่ออินเทอร์เน็ตก่อนเปิดข้อมูลต้นทาง" /></div> : null}
      <DocumentRegister key={`${companyId}:${branchId}:${stationKey}`} entries={entries} online={online} />

      <section aria-label="ค้นหาประเภทเอกสาร" className="mb-5 flex flex-col gap-3 sm:flex-row">
        <label className="relative flex-1">
          <span className="sr-only">ค้นหาประเภทเอกสาร</span>
          <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-400" />
          <Input className="min-h-11 bg-white pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="เช่น ใบสั่งซื้อ ใบสำคัญจ่าย" />
        </label>
        <select aria-label="หมวดเอกสาร" className="min-h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm" value={group} onChange={(event) => setGroup(event.target.value as DocumentGroup | "all")}>
          <option value="all">ทุกหมวดที่มีสิทธิ์</option>
          {availableGroups.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </section>
      <p className="mb-3 text-sm text-slate-500" aria-live="polite">แสดง {filtered.length} จาก {entries.length} ประเภทที่มีสิทธิ์</p>
      {filtered.length === 0 ? <CompanyStatePanel kind="empty" title="ไม่พบประเภทเอกสาร" description="ลองเปลี่ยนคำค้นหรือเลือกทุกหมวดที่มีสิทธิ์" /> : (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="ประเภทเอกสารที่มีสิทธิ์">
          {filtered.map((entry) => (
            <article key={entry.id} data-testid={`document-${entry.id}`} className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-3"><FileText className="h-5 w-5 shrink-0 text-blue-700" /><span className="text-xs font-semibold text-slate-500">{DOCUMENT_GROUPS[entry.group]}</span></div>
              <h2 className="mt-3 text-lg font-bold text-slate-950">{entry.title}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">{entry.description}</p>
              <p className="mb-4 mt-3 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">{entry.instruction}</p>
              {online ? <Button asChild variant="outline" className="mt-auto min-h-11"><Link to={entry.route} aria-label={`เปิด${entry.title}`}>เปิดระบบต้นทาง<ArrowRight className="ml-2 h-4 w-4" /></Link></Button> : <Button disabled variant="outline" className="mt-auto min-h-11">รอเชื่อมต่ออินเทอร์เน็ต</Button>}
            </article>
          ))}
        </section>
      )}
      <p className="mt-5 text-sm leading-6 text-slate-500">งานระยะถัดไป: ใบเสนอราคา ใบแจ้งหนี้ให้ลูกค้า ใบส่งของ ใบวางบิล และแม่แบบ A4 กลาง โดยแยกเหตุการณ์ธุรกิจและสิทธิ์ออกเอกสารให้ชัดเจน</p>
    </div>
  );
}
