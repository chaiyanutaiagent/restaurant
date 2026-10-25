import type { PairingProduct } from "./devicePairingLink";

// Immutable, explicitly published UAT artifacts; never use a mutable latest APK.
export const pairingApps: Record<PairingProduct, { name: string; download: string }> = {
  restaurant: { name: "Restaurant", download: "https://uat-pos.foodchainservice.com/downloads/native-pos-0.1.0-uat.6/foodchainservice-restaurant-0.1.0-uat.6.apk" },
  retail: { name: "Retail", download: "https://uat-retail.foodchainservice.com/downloads/native-pos-0.1.0-uat.14/foodchainservice-retail-0.1.0-uat.14.apk" },
  takeaway: { name: "Takeaway", download: "https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/foodchainservice-takeaway-store-1.1.0-uat.16.apk" },
};
export function pairingProduct(value: string | null): PairingProduct | null {
  return value === "retail" || value === "restaurant" || value === "takeaway" ? value : null;
}
