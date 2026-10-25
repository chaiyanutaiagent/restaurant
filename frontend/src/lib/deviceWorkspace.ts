import type { BranchDetail } from "@/types/admin";
import type { DeviceContext, DeviceType } from "@/types/device";

export function supportsDeviceType(branch: Pick<BranchDetail, "business_type" | "target_database">, type: DeviceType): boolean {
  return branch.business_type === branch.target_database && (
    branch.business_type === "restaurant"
    || (["retail_pos", "takeaway"].includes(branch.business_type ?? "") && type === "counter")
  );
}

export function counterSalesTarget(device: Pick<DeviceContext, "business_type" | "target_database">): { path: string; permission: string } | null {
  if (device.business_type !== device.target_database) return null;
  if (device.business_type === "retail_pos") return { path: "/retail/pos", permission: "pos.sale.create" };
  if (device.business_type === "restaurant") return { path: "/counter/orders", permission: "fb.order.create" };
  if (device.business_type === "takeaway") return { path: "/takeaway/store/orders", permission: "takeaway.sale.create" };
  return null;
}
