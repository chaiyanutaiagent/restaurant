// Explicit UAT alias: never infer an environment from an arbitrary tenant name.
export const SKETCH_BIZ_UAT = {
  hostname: "sketchbiz.foodchainservice.com",
  slug: "sketch-biz",
  companyId: "1b8a1818-44d6-4d5f-9d22-e5e17b23c081",
  displayName: "SKETCH BIZ",
};

export const THE_LOFT_UAT = {
  hostname: "theloft.foodchainservice.com",
  slug: "theloft",
  companyId: "9b766136-c10f-4ef4-856f-b2f95b943f5e",
  displayName: "THE LOFT",
};

export function tenantHost(hostname: string) {
  const normalized = hostname.toLowerCase().split(":")[0];
  return [SKETCH_BIZ_UAT, THE_LOFT_UAT].find((tenant) => tenant.hostname === normalized) ?? null;
}
