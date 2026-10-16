// Explicit UAT alias: never infer an environment from an arbitrary tenant name.
export const SKETCH_BIZ_UAT = {
  hostname: "sketchbiz.foodchainservice.com",
  slug: "sketch-biz",
  companyId: "1b8a1818-44d6-4d5f-9d22-e5e17b23c081",
};

export function tenantHost(hostname: string) {
  return hostname.toLowerCase().split(":")[0] === SKETCH_BIZ_UAT.hostname
    ? SKETCH_BIZ_UAT : null;
}
