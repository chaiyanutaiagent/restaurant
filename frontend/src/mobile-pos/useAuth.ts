import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { onboardingApi } from "./api";
import { useAuthStore, clearSession } from "./session";
import { cleanupStoreData } from "./storeDb";
import { assertNoNativeDraft } from "../lib/nativePosWorkGuard";

export function useLogout(_destination?: string): () => void {
  const client = useQueryClient(), navigate = useNavigate();
  return () => { void (async () => {
    try {
      assertNoNativeDraft();
      if (client.isMutating()) throw new Error("กำลังบันทึกรายการ กรุณารอ");
      await client.cancelQueries();
      await cleanupStoreData();
      await onboardingApi.post("/auth/logout", { refresh_token: useAuthStore.getState().refreshToken });
      await clearSession(); client.clear(); navigate("/", { replace: true });
    } catch (error) { alert(error instanceof Error ? error.message : "ออกจากระบบไม่สำเร็จ"); }
  })(); };
}
