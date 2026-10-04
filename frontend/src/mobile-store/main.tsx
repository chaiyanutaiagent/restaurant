import React from "react";
import ReactDOM from "react-dom/client";
import { Capacitor } from "@capacitor/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "@/components/ui/toaster";
import StoreApp from "./StoreApp";
import UpdateGate from "./UpdateGate";
import TakeawayDeviceSettingsPage from "@/pages/takeaway/TakeawayDeviceSettingsPage";
import "../index.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
document.title = "Foodchainservice Takeaway Store UAT";
if (Capacitor.isNativePlatform()) {
  document.documentElement.classList.add("native-app", `native-${Capacitor.getPlatform()}`);
}
ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><StoreApp DevicePage={TakeawayDeviceSettingsPage} /><UpdateGate /><Toaster /></BrowserRouter></QueryClientProvider></React.StrictMode>);
