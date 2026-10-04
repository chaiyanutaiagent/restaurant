import { useMutation } from "@tanstack/react-query";
import { FlaskConical, KeyRound } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";
import type { QaPersona } from "@/types/auth";

export default function QaAccessPanel({ defaultDestination }: { defaultDestination: string }): JSX.Element {
  const [accessKey, setAccessKey] = useState("");
  const [personas, setPersonas] = useState<QaPersona[]>([]);
  const [personaKey, setPersonaKey] = useState("");
  const [branchId, setBranchId] = useState("");
  const setSession = useAuthStore((state) => state.setSession);
  const navigate = useNavigate();
  const location = useLocation();
  const next = new URLSearchParams(location.search).get("next");
  const redirectTo = next?.startsWith("/") && !next.startsWith("//") ? next : defaultDestination;
  const selected = useMemo(() => personas.find((item) => item.key === personaKey) ?? null, [personaKey, personas]);
  const load = useMutation({
    mutationFn: async () => (await authApi.qaPersonas(accessKey)).data.data,
    onSuccess: (items) => {
      setPersonas(items);
      const first = items[0];
      setPersonaKey(first?.key ?? "");
      setBranchId(first?.branches.find((item) => item.is_default)?.id ?? first?.branches[0]?.id ?? "");
    },
  });
  const open = useMutation({
    mutationFn: async () => {
      if (!selected?.company_id) throw new Error("ไม่พบ Company ของ Persona");
      const response = await authApi.qaSession(accessKey, selected.key, branchId || null);
      return { companyId: selected.company_id, session: response.data.data };
    },
    onSuccess: ({ companyId, session }) => {
      setSession(session, companyId);
      window.localStorage.setItem("last_company_id", companyId);
      navigate(redirectTo, { replace: true });
    },
  });
  const error = load.error ?? open.error;
  return <section className="mb-5 rounded-xl border border-amber-300 bg-amber-50 p-4" data-testid="qa-access-panel"><div className="flex items-center gap-2 font-black text-amber-950"><FlaskConical className="h-5 w-5" />QA Access Mode · UAT/Local เท่านั้น</div><p className="mt-1 text-xs text-amber-900">ข้ามเฉพาะการกรอกบัญชี สิทธิ์และขอบเขตยังตรวจจาก Server ตาม Persona จริง</p><div className="mt-3 space-y-2"><Input type="password" autoComplete="off" value={accessKey} onChange={(event) => setAccessKey(event.target.value)} placeholder="QA access key" aria-label="QA access key" />{personas.length === 0 ? <Button type="button" variant="outline" className="w-full" disabled={load.isPending || accessKey.length < 1} onClick={() => load.mutate()}><KeyRound className="h-4 w-4" />{load.isPending ? "กำลังตรวจ..." : "เปิดรายการ Test Persona"}</Button> : <><select className="min-h-11 w-full rounded-md border border-amber-300 bg-white px-3" value={personaKey} onChange={(event) => { const nextPersona = personas.find((item) => item.key === event.target.value); setPersonaKey(event.target.value); setBranchId(nextPersona?.branches.find((item) => item.is_default)?.id ?? nextPersona?.branches[0]?.id ?? ""); }}>{personas.map((item) => <option key={item.key} value={item.key}>{item.label} · {item.company_name}</option>)}</select>{selected?.branches.length ? <select className="min-h-11 w-full rounded-md border border-amber-300 bg-white px-3" value={branchId} onChange={(event) => setBranchId(event.target.value)}>{selected.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name} · {branch.code}</option>)}</select> : null}<Button type="button" className="w-full" disabled={open.isPending} onClick={() => open.mutate()}>{open.isPending ? "กำลังออก Session..." : "เข้าใช้งานด้วย Persona นี้"}</Button></>}</div>{error ? <p className="mt-2 text-xs font-bold text-red-700">ไม่สามารถเปิด QA Mode ได้ กรุณาตรวจ key, host และ kill switch</p> : null}</section>;
}
