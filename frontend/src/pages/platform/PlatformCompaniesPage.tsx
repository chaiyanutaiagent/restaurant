import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Plus, Search } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { platformApi, platformErrorMessage } from "@/lib/platformApi";
import type { PlatformCompanyCreate } from "@/types/platform";

const initialForm: PlatformCompanyCreate = {
  name: "",
  name_en: "",
  tax_id: "",
  email: "",
  phone: "",
  currency: "THB",
  timezone: "Asia/Bangkok",
  plan_code: "starter",
  feature_flags: { restaurant: true, retail_pos: false, takeaway: false },
  plan_limits: { brands: 1, branches: 1, users: 10, devices: 3 },
  owner: { username: "", password: "", email: "", display_name: "" },
  reason: "เปิด Company ใหม่ตามคำขอลูกค้า"
};

export default function PlatformCompaniesPage(): JSX.Element {
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<PlatformCompanyCreate>(initialForm);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const companies = useQuery({
    queryKey: ["platform", "companies", search],
    queryFn: async () => (await platformApi.companies(search)).data.data
  });
  const createCompany = useMutation({
    mutationFn: () => platformApi.createCompany(form),
    onSuccess: (response) => {
      void queryClient.invalidateQueries({ queryKey: ["platform", "companies"] });
      navigate(`/platform/companies/${response.data.data.id}`);
    }
  });

  const updateLimit = (key: string, value: string) => {
    setForm((current) => ({
      ...current,
      plan_limits: { ...current.plan_limits, [key]: Math.max(Number(value) || 0, 0) }
    }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    createCompany.mutate();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-emerald-300">Tenant lifecycle</p>
          <h2 className="mt-1 text-3xl font-bold">บริษัทลูกค้า</h2>
          <p className="mt-2 text-sm text-slate-400">สร้างร้านใหม่ได้โดยไม่แก้ source code หรือ SQL</p>
        </div>
        <Button className="bg-emerald-400 text-slate-950 hover:bg-emerald-300" onClick={() => setShowCreate((value) => !value)}>
          <Plus className="h-4 w-4" /> เปิด Company ใหม่
        </Button>
      </div>

      {showCreate ? (
        <form className="rounded-2xl border border-slate-700 bg-slate-900 p-6" onSubmit={submit}>
          <h3 className="text-xl font-semibold">Company และ Owner คนแรก</h3>
          <p className="mt-1 text-sm text-slate-400">Owner จะได้สิทธิ์ระดับ Company แต่ไม่ใช่ Platform Owner</p>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <Field label="ชื่อบริษัท *"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
            <Field label="ชื่ออังกฤษ"><Input value={form.name_en ?? ""} onChange={(e) => setForm({ ...form, name_en: e.target.value })} /></Field>
            <Field label="เลขประจำตัวผู้เสียภาษี"><Input value={form.tax_id ?? ""} onChange={(e) => setForm({ ...form, tax_id: e.target.value })} /></Field>
            <Field label="อีเมลบริษัท"><Input type="email" value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="ชื่อ Company Owner *"><Input value={form.owner.display_name} onChange={(e) => setForm({ ...form, owner: { ...form.owner, display_name: e.target.value } })} required /></Field>
            <Field label="Username Owner *"><Input value={form.owner.username} onChange={(e) => setForm({ ...form, owner: { ...form.owner, username: e.target.value } })} required /></Field>
            <Field label="อีเมล Owner"><Input type="email" value={form.owner.email ?? ""} onChange={(e) => setForm({ ...form, owner: { ...form.owner, email: e.target.value } })} /></Field>
            <Field label="รหัสผ่านชั่วคราว Owner (อย่างน้อย 12 ตัว) *"><Input type="password" minLength={12} value={form.owner.password} onChange={(e) => setForm({ ...form, owner: { ...form.owner, password: e.target.value } })} required /></Field>
            <Field label="Plan code"><Input value={form.plan_code} onChange={(e) => setForm({ ...form, plan_code: e.target.value })} required /></Field>
            <Field label="เหตุผลที่เปิด Company *"><Input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} required /></Field>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-4">
            {Object.entries(form.plan_limits).map(([key, value]) => (
              <Field key={key} label={`Limit: ${key}`}>
                <Input type="number" min={0} value={value} onChange={(event) => updateLimit(key, event.target.value)} />
              </Field>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-5 text-sm">
            {Object.entries(form.feature_flags).map(([key, enabled]) => (
              <label key={key} className="flex items-center gap-2 text-slate-300">
                <input type="checkbox" checked={enabled} onChange={(event) => setForm({ ...form, feature_flags: { ...form.feature_flags, [key]: event.target.checked } })} />
                Feature: {key}
              </label>
            ))}
          </div>
          {createCompany.error ? <p className="mt-4 text-sm text-red-300">{platformErrorMessage(createCompany.error)}</p> : null}
          <div className="mt-6 flex gap-3">
            <Button className="bg-emerald-400 text-slate-950 hover:bg-emerald-300" disabled={createCompany.isPending}>{createCompany.isPending ? "กำลังสร้าง..." : "สร้าง Company และ Owner"}</Button>
            <Button type="button" variant="outline" onClick={() => setShowCreate(false)}>ยกเลิก</Button>
          </div>
        </form>
      ) : null}

      <div className="relative max-w-xl">
        <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
        <Input className="border-slate-700 bg-slate-900 pl-10 text-slate-100" placeholder="ค้นหาชื่อบริษัท เลขภาษี หรืออีเมล" value={search} onChange={(event) => setSearch(event.target.value)} />
      </div>

      {companies.isLoading ? <p className="text-slate-400">กำลังโหลด...</p> : null}
      {companies.error ? <p className="text-red-300">{platformErrorMessage(companies.error)}</p> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {companies.data?.map((company) => (
          <Link key={company.id} to={`/platform/companies/${company.id}`} className="rounded-xl border border-slate-700 bg-slate-900 p-5 transition hover:border-emerald-400">
            <div className="flex items-start justify-between gap-3">
              <div className="flex gap-3">
                <div className="rounded-lg bg-slate-800 p-2"><Building2 className="h-5 w-5 text-emerald-300" /></div>
                <div><h3 className="font-semibold">{company.name}</h3><p className="mt-1 text-xs text-slate-400">{company.id}</p></div>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${company.is_active ? "bg-emerald-400/15 text-emerald-300" : "bg-red-400/15 text-red-300"}`}>{company.is_active ? "ACTIVE" : "SUSPENDED"}</span>
            </div>
            <div className="mt-5 flex justify-between text-sm text-slate-400"><span>Plan: {company.plan_code}</span><span>Generation {company.credential_version}</span></div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return <div className="space-y-2"><Label className="text-slate-300">{label}</Label>{children}</div>;
}
