export const nativeProduct = import.meta.env.VITE_NATIVE_POS_PRODUCT as "retail" | "restaurant" | undefined;
export const nativeBusinessType = nativeProduct === "retail" ? "retail_pos" : "restaurant";
export const nativeTitle = nativeProduct === "retail" ? "Foodchainservice Retail" : "Foodchainservice Restaurant";
export const nativeHome = `/${nativeProduct}/pos`;

// This is a client safety check. Server authentication and permissions remain authoritative.
export function assertNativeRequest(path: string, method: string, state: {
  businessType: string | null; targetDatabase: string | null; companyId: string | null;
  brandId: string | null; branchId: string | null;
}, online: boolean): void {
  if (!nativeProduct) return;
  if (!online && !["get", "head", "options"].includes(method.toLowerCase())) {
    throw new Error("รุ่นทดสอบนี้ต้องออนไลน์ก่อนบันทึกหรือรับชำระเงิน");
  }
  const pathname = path.split("?")[0];
  if (/^\/membership\/businesses\/[a-z0-9-]+$/.test(pathname)
      || ["/auth/login", "/auth/refresh", "/auth/logout", "/auth/me", "/auth/switch-branch", "/system/me/branches"].includes(pathname)) return;
  if (/^\/(auth\/(uat|qa)|platform|company-kitchen|takeaway)(\/|$)/.test(pathname)
      || (nativeProduct === "retail" && /^\/(restaurant|fb|wap)(\/|$)/.test(pathname))
      || (nativeProduct === "restaurant" && /^\/retail(\/|$)/.test(pathname))) {
    throw new Error("แอปนี้ไม่เปิดพื้นที่งานดังกล่าว");
  }
  if (state.businessType !== nativeBusinessType || state.targetDatabase !== nativeBusinessType
      || !state.companyId || !state.brandId || !state.branchId) {
    throw new Error("เลือกสาขาของแอปนี้และยืนยันสิทธิ์กับ Server ก่อนทำงาน");
  }
}
