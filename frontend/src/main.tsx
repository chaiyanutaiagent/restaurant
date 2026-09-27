import React from "react";
import ReactDOM from "react-dom/client";
import { Capacitor } from "@capacitor/core";
import { registerSW } from "virtual:pwa-register";
import App from "./App";
import "./index.css";
import { PLATFORM_BRAND } from "@/config/platformBrand";

registerSW({ immediate: true });
document.title = PLATFORM_BRAND.productName;

if (Capacitor.isNativePlatform()) {
  const platform = Capacitor.getPlatform();
  document.documentElement.classList.add("native-app", `native-${platform}`);
  document.documentElement.dataset.nativePlatform = platform;
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
