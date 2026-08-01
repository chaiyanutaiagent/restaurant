import type { CapacitorConfig } from "@capacitor/cli";

const isUatBuild = process.env.CAPACITOR_UAT === "true";

const config: CapacitorConfig = {
  appId: "com.chaiyanutaiagent.restaurant",
  appName: "Restaurant POS",
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
