import React from "react";
import ReactDOM from "react-dom/client";
import { registerSW } from "virtual:pwa-register";
import App from "./App";
import "./index.css";
import { PLATFORM_BRAND } from "@/config/platformBrand";

registerSW({ immediate: true });
document.title = PLATFORM_BRAND.productName;

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
