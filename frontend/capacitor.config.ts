import type { CapacitorConfig } from "@capacitor/cli";

const isUatBuild = process.env.CAPACITOR_UAT === "true";

const config: CapacitorConfig = {
  appId: "com.foodchainservice.takeaway",
  appName: "Foodchainservice Takeaway Store",
  webDir: isUatBuild ? "dist-mobile-store" : "dist",
  android: {
    allowMixedContent: false,
  },
  server: {
    androidScheme: "https",
    cleartext: false,
  },
};

export default config;
