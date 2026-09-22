import { FlaskConical } from "lucide-react";
import { useAuthStore } from "@/stores/auth.store";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";

function tokenPersona(token: string | null): string | null {
  if (!token) return null;
  try {
    const value = token.split(".")[1];
    if (!value) return null;
    const parsed = JSON.parse(window.atob(value.replace(/-/g, "+").replace(/_/g, "/"))) as { qa_mode?: boolean; qa_persona?: string };
    return parsed.qa_mode ? parsed.qa_persona ?? "qa" : null;
  } catch { return null; }
}

export default function QaModeBanner(): JSX.Element | null {
  const tenantPersona = useAuthStore((state) => state.qaPersona);
  const companyId = useAuthStore((state) => state.companyId);
  const branchId = useAuthStore((state) => state.branchId);
  const platformToken = usePlatformAuthStore((state) => state.accessToken);
  const platformPersona = tokenPersona(platformToken);
  const persona = tenantPersona ?? platformPersona;
  if (!persona) return null;
  return <div className="fixed inset-x-0 bottom-0 z-[100] flex min-h-8 items-center justify-center gap-2 border-t border-amber-400 bg-amber-300 px-3 py-1 text-center text-xs font-black text-amber-950 shadow-lg" data-testid="qa-mode-banner"><FlaskConical className="h-4 w-4" />QA MODE · {persona}{companyId ? ` · Company ${companyId.slice(0, 8)}` : " · Platform"}{branchId ? ` · Branch ${branchId.slice(0, 8)}` : " · Company scope"}</div>;
}
