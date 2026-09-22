import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { PlatformOperator, PlatformTokenResponse } from "@/types/platform";

type PlatformAuthState = {
  accessToken: string | null;
  csrfToken: string | null;
  sessionId: string | null;
  operator: PlatformOperator | null;
  setSession: (session: PlatformTokenResponse) => void;
  setOperator: (operator: PlatformOperator) => void;
  clearSession: () => void;
  isAuthenticated: () => boolean;
};

export const usePlatformAuthStore = create<PlatformAuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      csrfToken: null,
      sessionId: null,
      operator: null,
      setSession: (session) => set({
        accessToken: session.access_token,
        csrfToken: session.csrf_token,
        sessionId: session.session_id,
        operator: session.operator,
      }),
      setOperator: (operator) => set({ operator }),
      clearSession: () => set({ accessToken: null, csrfToken: null, sessionId: null, operator: null }),
      isAuthenticated: () => Boolean(get().accessToken && get().operator?.is_active)
    }),
    {
      name: "restaurant-platform-auth",
      storage: createJSONStorage(() => sessionStorage)
    }
  )
);

if (typeof window !== "undefined") {
  window.localStorage.removeItem("restaurant-platform-auth");
}
