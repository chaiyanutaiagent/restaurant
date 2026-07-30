import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth.store";

export function usePermission(code: string): boolean {
  return useAuthStore((state) => state.hasPermission(code));
}

export function useRequirePermission(code: string): void {
  const navigate = useNavigate();
  const hasPermission = usePermission(code);

  useEffect(() => {
    if (!hasPermission) {
      navigate("/403", { replace: true });
    }
  }, [hasPermission, navigate]);
}
