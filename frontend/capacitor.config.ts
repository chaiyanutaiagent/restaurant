import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.chaiyanutaiagent.restaurant",
  appName: "Restaurant POS",
  webDir: "dist",
  server: {
    androidScheme: "https",
  },
};

export default config;
