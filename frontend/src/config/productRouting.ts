export type ProductWorkspace = "company" | "restaurant" | "retail" | "takeaway";

export type ProductBusinessType = "restaurant" | "retail_pos" | "takeaway";

export const PRODUCT_ENTRY_PATH: Record<ProductWorkspace, string> = {
  company: "/company",
  restaurant: "/restaurant",
  retail: "/retail",
  takeaway: "/takeaway",
};

export const PRODUCT_POS_PATH: Record<ProductBusinessType, string> = {
  restaurant: "/restaurant/pos",
  retail_pos: "/retail/pos",
  takeaway: "/takeaway/store/orders",
};

const WORKSPACE_HOST_LABEL: Record<ProductWorkspace, string> = {
  company: "app",
  restaurant: "restaurant",
  retail: "retail",
  takeaway: "takeaway",
};

export function workspaceFromHostname(hostname: string): ProductWorkspace | null {
  const normalized = hostname.trim().toLowerCase().split(":", 1)[0];
  if (!normalized.endsWith(".foodchainservice.com")) return null;
  const label = normalized.split(".")[0].replace(/^uat-/, "");
  if (label === "app") return "company";
  if (label === "restaurant" || label === "retail" || label === "takeaway") return label;
  return null;
}

export function workspaceHost(workspace: ProductWorkspace, hostname: string): string | null {
  const normalized = hostname.trim().toLowerCase().split(":", 1)[0];
  if (!normalized.endsWith(".foodchainservice.com")) return null;
  const isUat = normalized.startsWith("uat-");
  return `${isUat ? "uat-" : ""}${WORKSPACE_HOST_LABEL[workspace]}.foodchainservice.com`;
}

export function workspaceUrl(
  workspace: ProductWorkspace,
  path = PRODUCT_ENTRY_PATH[workspace],
  location: Pick<Location, "hostname" | "protocol"> = window.location,
): string {
  const targetHost = workspaceHost(workspace, location.hostname);
  if (!targetHost) return path;
  return `${location.protocol}//${targetHost}${path}`;
}

export function businessTypeWorkspace(businessType: ProductBusinessType): Exclude<ProductWorkspace, "company"> {
  if (businessType === "retail_pos") return "retail";
  return businessType;
}
