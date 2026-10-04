import { FlaskConical } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useAuthStore } from "@/stores/auth.store";
import { usePlatformAuthStore } from "@/stores/platform-auth.store";

type QaTokenContext = {
  persona: string;
  expiresAt: number | null;
};

function tokenContext(token: string | null): QaTokenContext | null {
  if (!token) return null;
  try {
    const value = token.split(".")[1];
    if (!value) return null;
    const parsed = JSON.parse(window.atob(value.replace(/-/g, "+").replace(/_/g, "/"))) as {
      exp?: number;
      qa_deadline?: number;
      qa_mode?: boolean;
      qa_persona?: string;
    };
    if (!parsed.qa_mode) return null;
    return {
      persona: parsed.qa_persona ?? "qa",
      expiresAt: parsed.qa_deadline ?? parsed.exp ?? null,
    };
  } catch { return null; }
}

export default function QaModeBanner(): JSX.Element | null {
  const { pathname } = useLocation();
  const tenantToken = useAuthStore((state) => state.accessToken);
  const companyId = useAuthStore((state) => state.companyId);
  const branchId = useAuthStore((state) => state.branchId);
  const platformToken = usePlatformAuthStore((state) => state.accessToken);
  const isPlatformSurface = pathname === "/platform" || pathname.startsWith("/platform/");
  const context = tokenContext(isPlatformSurface ? platformToken : tenantToken);
  if (!context) return null;
  const scope = isPlatformSurface
    ? " · Platform"
    : `${companyId ? ` · Company ${companyId.slice(0, 8)}` : " · Company"}${branchId ? ` · Branch ${branchId.slice(0, 8)}` : " · Company scope"}`;
  const expiry = context.expiresAt
    ? ` · หมดอายุ ${new Date(context.expiresAt * 1000).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" })}`
    : "";
  return <div className="fixed inset-x-0 bottom-0 z-[100] flex min-h-8 items-center justify-center gap-2 border-t border-amber-400 bg-amber-300 px-3 py-1 text-center text-xs font-black text-amber-950 shadow-lg" data-testid="qa-mode-banner"><FlaskConical className="h-4 w-4" />QA MODE · {context.persona}{scope}{expiry}</div>;
}
