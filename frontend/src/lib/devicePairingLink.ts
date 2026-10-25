export type PairingProduct = "retail" | "restaurant" | "takeaway";
export type PairingLink = {
  companyId: string; deviceCode: string; pin: string;
  branchId: string | null; businessCode: string | null; expiresAt: number | null;
};

export function parseDevicePairingLink(raw: string, product: PairingProduct, now = Date.now()): PairingLink {
  const url = new URL(raw.trim());
  const web = url.protocol === "https:" && (url.hostname === "foodchainservice.com" || url.hostname.endsWith(".foodchainservice.com"))
    && (!url.port || url.port === "443") && ["/device/pair", `/device/pair/${product}`].includes(url.pathname);
  const app = url.protocol === `foodchainservice-${product}-uat:` && url.hostname === "pair" && ["", "/"].includes(url.pathname);
  if ((!web && !app) || url.username || url.password) throw new Error("ใช้ QR จับคู่เครื่องของ Foodchainservice สำหรับแอปนี้เท่านั้น");
  const get = (key: string) => {
    if (url.searchParams.getAll(key).length > 1) throw new Error("QR มีข้อมูลซ้ำ ไม่สามารถจับคู่ได้");
    return url.searchParams.get(key);
  };
  const target = get("target_app");
  if (target && target !== product) throw new Error("QR นี้เป็นของแอปคนละระบบ");
  const companyId = get("company_id") ?? "";
  const branchId = get("branch_id");
  const deviceCode = get("device_code") ?? "";
  const pin = get("pin") ?? "";
  const businessCode = get("business_code");
  const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
  const expiry = get("expires_at");
  const expiresAt = expiry ? Date.parse(expiry) : null;
  if (!uuid.test(companyId) || (branchId && !uuid.test(branchId)) || !/^C-[A-Z0-9]{6,40}$/.test(deviceCode) || !/^\d{6}$/.test(pin)
      || (businessCode && !/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/.test(businessCode))) throw new Error("QR จับคู่เครื่องไม่สมบูรณ์ กรุณาขอ QR ใหม่จากหลังบ้าน");
  if (expiresAt !== null && (!Number.isFinite(expiresAt) || expiresAt <= now)) throw new Error("QR หมดอายุแล้ว กรุณากด PIN ใหม่จากหลังบ้าน");
  return { companyId: companyId.toLowerCase(), branchId: branchId?.toLowerCase() ?? null, deviceCode, pin, businessCode, expiresAt };
}

export function androidPairingIntent(webUrl: string, product: PairingProduct): string {
  const url = new URL(webUrl);
  return `intent://pair?${url.searchParams.toString()}#Intent;scheme=foodchainservice-${product}-uat;package=com.foodchainservice.${product}.uat;S.browser_fallback_url=${encodeURIComponent(webUrl)};end`;
}
