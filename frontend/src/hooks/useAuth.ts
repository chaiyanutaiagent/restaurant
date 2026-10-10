import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { authApi } from "@/lib/api";
import { db } from "@/lib/db";
import { clearOfflineEncryptionKeyWhenSafe } from "@/lib/secureOfflineStore";
import { useAuthStore } from "@/stores/auth.store";
import type { LoginRequest } from "@/types/auth";

function getLoginErrorMessage(error: unknown): string | null {
  if (!error) return null;
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 401) {
      return "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง";
    }
    if (!error.response) {
      return "เชื่อมต่อระบบไม่ได้ กรุณาตรวจสอบเครือข่ายแล้วลองอีกครั้ง";
    }
    const detail = error.response.data?.detail ?? error.response.data?.error?.message;
    if (typeof detail === "string") return detail;
  }
  return error instanceof Error ? error.message : "เข้าสู่ระบบไม่สำเร็จ";
}

export function useLogin(defaultDestination = "/admin", expectedBusinessSlug?: string): {
  login: (payload: LoginRequest) => Promise<void>;
  isLoading: boolean;
  error: string | null;
} {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const setSession = useAuthStore((state) => state.setSession);
  const next = new URLSearchParams(location.search).get("next");
  const safeNext = next?.startsWith("/") && !next.startsWith("//") && !next.includes("\\") ? next : null;
  const canonicalPath = expectedBusinessSlug ? `/${expectedBusinessSlug}/admin` : null;
  const redirectTo = canonicalPath
    ? (safeNext && (safeNext === canonicalPath || safeNext.startsWith(`${canonicalPath}?`) || safeNext.startsWith(`${canonicalPath}#`)) ? safeNext : canonicalPath)
    : safeNext ?? defaultDestination;

  const mutation = useMutation({
    mutationFn: async (payload: LoginRequest) => {
      const companyId = payload.company_id;
      if (!companyId) {
        throw new Error("กรุณากรอก Company ID");
      }

      const loginPath = window.location.pathname;
      const response = await authApi.login(payload, companyId);
      if (!active.current || window.location.pathname !== loginPath) {
        throw new Error("ลิงก์เข้าสู่ระบบเปลี่ยนแล้ว กรุณาเข้าสู่ระบบอีกครั้ง");
      }
      if (response.data.data.user.company_id !== companyId
        || (expectedBusinessSlug && response.data.data.business_slug !== expectedBusinessSlug)) {
        throw new Error("บัญชีที่ได้รับไม่ตรงกับบริษัทในลิงก์ ระบบยังไม่เข้าสู่ระบบ กรุณาลองใหม่หรือติดต่อผู้ดูแล");
      }
      if (expectedBusinessSlug) {
        let tokenCompanyId: unknown;
        try {
          const encoded = response.data.data.access_token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
          tokenCompanyId = JSON.parse(window.atob(encoded)).company_id;
        } catch { /* Malformed identity fails closed; API remains responsible for JWT verification. */ }
        if (tokenCompanyId !== companyId) throw new Error("ข้อมูล session ไม่ตรงกับบริษัทในลิงก์ กรุณาติดต่อผู้ดูแล");
      }
      return { companyId, tokenResponse: response.data.data, loginPath };
    },
    onSuccess: async ({ companyId, tokenResponse, loginPath }) => {
      // Do not reuse cached business data after switching identities.
      await queryClient.cancelQueries();
      if (!active.current || window.location.pathname !== loginPath) return;
      queryClient.clear();
      setSession(tokenResponse, companyId);
      window.localStorage.setItem("last_company_id", companyId);
      navigate(redirectTo, { replace: true });
    }
  });

  return {
    login: async (payload) => {
      try { await mutation.mutateAsync(payload); } catch { /* Render the mutation error in the form. */ }
    },
    isLoading: mutation.isPending,
    error: getLoginErrorMessage(mutation.error)
  };
}

export function useUatAutoLogin(defaultDestination = "/admin"): {
  startAutoLogin: () => void;
  isLoading: boolean;
} {
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useAuthStore((state) => state.setSession);
  const next = new URLSearchParams(location.search).get("next");
  const redirectTo = next?.startsWith("/") && !next.startsWith("//") ? next : defaultDestination;

  const mutation = useMutation({
    mutationFn: async () => (await authApi.uatAutoLogin()).data.data,
    onSuccess: (tokenResponse) => {
      // An in-flight generic QA login must not take over a canonical company page.
      if (window.location.pathname !== "/login") return;
      const companyId = tokenResponse.user.company_id;
      setSession(tokenResponse, companyId);
      window.localStorage.setItem("last_company_id", companyId);
      navigate(redirectTo, { replace: true });
    }
  });

  return {
    startAutoLogin: mutation.mutate,
    isLoading: mutation.isPending
  };
}

export function useLogout(destination = "/login"): () => void {
  const navigate = useNavigate();
  const clearSession = useAuthStore((state) => state.clearSession);

  return () => {
    void (async () => {
      const [restaurantOrders, pendingSales] = await Promise.all([
        db.restaurantPendingOrders.toArray(),
        db.pendingSales.toArray(),
      ]);
      const hasPendingRestaurant = restaurantOrders.some((order) => !["reconciled", "rejected"].includes(order.status));
      const hasPendingPos = pendingSales.some((sale) => !sale.synced);
      if (hasPendingRestaurant || hasPendingPos) {
        window.alert("ยังมีรายการขายที่ส่งไม่สำเร็จ กรุณาต่ออินเทอร์เน็ตและซิงก์ข้อมูลก่อนออกจากระบบ เพื่อรักษาชื่อพนักงานขายให้ถูกต้อง");
        return;
      }
      const refreshToken = useAuthStore.getState().refreshToken;
      if (refreshToken) {
        void authApi.logout(refreshToken);
      }
      await clearOfflineEncryptionKeyWhenSafe();
      clearSession();
      navigate(destination, { replace: true });
    })();
  };
}

export function useMe() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const response = await authApi.me();
      return response.data.data;
    },
    enabled: isAuthenticated()
  });
}
