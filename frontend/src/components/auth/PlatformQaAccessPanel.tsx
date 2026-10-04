import { useMutation } from "@tanstack/react-query";
import { FlaskConical, KeyRound } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { platformApi } from "@/lib/platformApi";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";
import type { QaPersona } from "@/types/auth";

export default function PlatformQaAccessPanel(): JSX.Element {
  const [accessKey, setAccessKey] = useState("");
  const [personas, setPersonas] = useState<QaPersona[]>([]);
  const [persona, setPersona] = useState("");
  const setSession = usePlatformAuthStore((state) => state.setSession);
  const navigate = useNavigate();
  const load = useMutation({ mutationFn: async () => (await platformApi.qaPersonas(accessKey)).data.data, onSuccess: (items) => { setPersonas(items); setPersona(items[0]?.key ?? ""); } });
  const open = useMutation({ mutationFn: async () => (await platformApi.qaSession(accessKey, persona)).data.data, onSuccess: (session) => { setSession(session); navigate("/platform/dashboard", { replace: true }); } });
  return <section className="mb-5 rounded-xl border border-amber-500/60 bg-amber-950/40 p-4" data-testid="platform-qa-access-panel"><div className="flex items-center gap-2 font-bold text-amber-200"><FlaskConical className="h-5 w-5" />QA Access Mode</div><p className="mt-1 text-xs text-amber-100/80">Session อายุสั้นและใช้สิทธิ์ Platform จริงของ Persona</p><div className="mt-3 space-y-2"><Input className="border-slate-600 bg-slate-950" type="password" autoComplete="off" value={accessKey} onChange={(event) => setAccessKey(event.target.value)} placeholder="QA access key" />{personas.length === 0 ? <Button type="button" variant="outline" className="w-full" disabled={load.isPending || !accessKey} onClick={() => load.mutate()}><KeyRound className="h-4 w-4" />เปิดรายการ Test Persona</Button> : <><select className="min-h-11 w-full rounded-md border border-slate-600 bg-slate-950 px-3" value={persona} onChange={(event) => setPersona(event.target.value)}>{personas.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select><Button type="button" className="w-full bg-amber-300 text-slate-950 hover:bg-amber-200" disabled={open.isPending || !persona} onClick={() => open.mutate()}>เข้า Platform ด้วย Persona นี้</Button></>}</div>{load.error || open.error ? <p className="mt-2 text-xs font-bold text-red-300">เปิด QA Mode ไม่สำเร็จ กรุณาตรวจ key, host และ kill switch</p> : null}</section>;
}
