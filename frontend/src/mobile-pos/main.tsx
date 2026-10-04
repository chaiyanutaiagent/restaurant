import React from "react";
import ReactDOM from "react-dom/client";
import { Capacitor } from "@capacitor/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "@/components/ui/toaster";
import PosApp from "./App";
import ConnectionStatus from "./ConnectionStatus";
import { installNativeDocumentPrint } from "../lib/nativeDocumentPrint";
import "../index.css";
import "./mobile-pos.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
document.title = "Foodchainservice POS UAT";
installNativeDocumentPrint();
document.documentElement.lang = "th";
document.documentElement.classList.add("mobile-pos");
if (Capacitor.isNativePlatform()) {
  document.documentElement.classList.add("native-app", `native-${Capacitor.getPlatform()}`);
  document.documentElement.dataset.nativePlatform = Capacitor.getPlatform();
}
ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode>
  <QueryClientProvider client={queryClient}><BrowserRouter>
    <ConnectionStatus /><PosApp /><Toaster />
  </BrowserRouter></QueryClientProvider>
</React.StrictMode>);
