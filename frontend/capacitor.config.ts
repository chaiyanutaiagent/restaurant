import type { CapacitorConfig } from "@capacitor/cli";

const isUatBuild = process.env.CAPACITOR_UAT === "true";

const config: CapacitorConfig = {
  appId: "com.foodchainservice.takeaway",
  appName: "Foodchainservice Takeaway",
  webDir: "dist",
  android: {
    allowMixedContent: isUatBuild,
  },
  server: {
    androidScheme: "https",
    cleartext: isUatBuild,
  },
};

export default config;
