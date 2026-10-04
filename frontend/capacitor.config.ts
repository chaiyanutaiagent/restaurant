import type { CapacitorConfig } from "@capacitor/cli";

const isUatBuild = process.env.CAPACITOR_UAT === "true";
const target = process.env.CAPACITOR_APP;
if (target && target !== "pos-uat") throw new Error("Unknown native app target; Production is on HOLD");
const isPosBuild = target === "pos-uat";

const config: CapacitorConfig = {
  appId: isPosBuild ? "com.foodchainservice.pos.uat" : "com.foodchainservice.takeaway",
  appName: isPosBuild ? "Foodchainservice POS UAT" : "Foodchainservice Takeaway Store",
  webDir: isPosBuild ? "dist-mobile-pos" : isUatBuild ? "dist-mobile-store" : "dist",
  ...(isPosBuild ? { ios: { path: "ios-pos", scheme: "App", contentInset: "never" as const } } : {}),
  android: {
    ...(isPosBuild ? { path: "android-pos" } : {}),
    allowMixedContent: false,
  },
  server: {
    androidScheme: "https",
    cleartext: false,
  },
};

export default config;
