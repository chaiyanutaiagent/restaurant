import type { CapacitorConfig } from "@capacitor/cli";

const isUatBuild = process.env.CAPACITOR_UAT === "true";
const posProduct = process.env.FCS_POS_PRODUCT;
if (posProduct && !["retail", "restaurant"].includes(posProduct)) throw new Error("Invalid POS product");
if (posProduct && !isUatBuild) throw new Error("Native POS Production remains on HOLD");

const config: CapacitorConfig = {
  appId: posProduct ? `com.foodchainservice.${posProduct}.uat` : "com.foodchainservice.takeaway",
  appName: posProduct ? `Foodchainservice ${posProduct === 'retail' ? 'Retail' : 'Restaurant'} UAT` : "Foodchainservice Takeaway Store",
  webDir: posProduct ? `dist-native-${posProduct}` : isUatBuild ? "dist-mobile-store" : "dist",
  android: {
    ...(posProduct ? { path: `android-${posProduct}` } : {}),
    allowMixedContent: false,
  },
  server: {
    androidScheme: "https",
    cleartext: false,
  },
};

export default config;
