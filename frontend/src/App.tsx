import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Capacitor } from "@capacitor/core";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import DeviceProtectedRoute from "@/components/auth/DeviceProtectedRoute";
import AppShell from "@/components/layout/AppShell";
import RestaurantShell from "@/components/layout/RestaurantShell";
import { Toaster } from "@/components/ui/toaster";
import { initAutoSync } from "@/lib/syncService";
import AccountingPage from "@/pages/accounting/AccountingPage";
import LoginPage from "@/pages/auth/LoginPage";
import AcceptInvitationPage from "@/pages/auth/AcceptInvitationPage";
import DashboardPage from "@/pages/dashboard/DashboardPage";
import ModuleSelectorPage from "@/pages/ModuleSelectorPage";
import StorefrontPage from "@/pages/storefront/StorefrontPage";
import BranchesPage from "@/pages/branches/BranchesPage";
import BranchSettingsPage from "@/pages/branches/BranchSettingsPage";
import CRMPage from "@/pages/crm/CRMPage";
import NotFoundPage from "@/pages/NotFoundPage";
import PayablePage from "@/pages/payable/PayablePage";
import POSPage from "@/pages/pos/POSPage";
import POSAdminPage from "@/pages/pos/POSAdminPage";
import POFormPage from "@/pages/purchase/POFormPage";
import PurchaseOrdersPage from "@/pages/purchase/PurchaseOrdersPage";
import SuppliersPage from "@/pages/purchase/SuppliersPage";
import ProductFormPage from "@/pages/products/ProductFormPage";
import ProductsPage from "@/pages/products/ProductsPage";
import UnitsPage from "@/pages/products/UnitsPage";
import ETaxPage from "@/pages/etax/ETaxPage";
import HRPage from "@/pages/hr/HRPage";
import IntegrationsPage from "@/pages/integrations/IntegrationsPage";
import ShipmentsPage from "@/pages/logistics/ShipmentsPage";
import SettingsPage from "@/pages/settings/SettingsPage";
import ReportsPage from "@/pages/reports/ReportsPage";
import ShiftHistoryPage from "@/pages/reports/ShiftHistoryPage";
import RolesPage from "@/pages/roles/RolesPage";
import MultiBranchStockPage from "@/pages/stock/MultiBranchStockPage";
import StockPage from "@/pages/stock/StockPage";
import CountingPage from "@/pages/stockCount/CountingPage";
import StockCountPage from "@/pages/stockCount/StockCountPage";
import TOFormPage from "@/pages/transfer/TOFormPage";
import TransferOrdersPage from "@/pages/transfer/TransferOrdersPage";
import UsersPage from "@/pages/users/UsersPage";
import FBSetupWizard from "@/pages/restaurant/FBSetupWizard";
import BrandAdminPage from "@/pages/restaurant/BrandAdminPage";
import RestaurantIndexPage from "@/pages/restaurant/RestaurantIndexPage";
import RestaurantAdminPage from "@/pages/restaurant/RestaurantAdminPage";
import RecipesPage from "@/pages/restaurant/RecipesPage";
import TableMapPage from "@/pages/restaurant/TableMapPage";
import KitchenDisplayPage from "@/pages/restaurant/KitchenDisplayPage";
import PickupDisplayPage from "@/pages/restaurant/PickupDisplayPage";
import CustomerMenuPage from "@/pages/restaurant/CustomerMenuPage";
import SessionCheckoutPage from "@/pages/restaurant/SessionCheckoutPage";
import FBSettingsPage from "@/pages/restaurant/FBSettingsPage";
import IngredientReportPage from "@/pages/restaurant/IngredientReportPage";
import FBOrdersPage from "@/pages/restaurant/FBOrdersPage";
import SessionDetailPage from "@/pages/restaurant/SessionDetailPage";
import QuickServicePage from "@/pages/restaurant/QuickServicePage";
import QRManagerPage from "@/pages/restaurant/QRManagerPage";
import WapOrderPage from "@/pages/restaurant/WapOrderPage";
import WapShiftClosePage from "@/pages/restaurant/WapShiftClosePage";
import RestaurantCentralCreditsPage from "@/pages/restaurant/RestaurantCentralCreditsPage";
import RestaurantCentralOrdersPage from "@/pages/restaurant/RestaurantCentralOrdersPage";
import RestaurantCentralProductionPage from "@/pages/restaurant/RestaurantCentralProductionPage";
import RestaurantCentralReportsPage from "@/pages/restaurant/RestaurantCentralReportsPage";
import RestaurantCentralStockPage from "@/pages/restaurant/RestaurantCentralStockPage";
import RestaurantStockCutoverPage from "@/pages/restaurant/RestaurantStockCutoverPage";
import RestaurantStoreCreditsPage from "@/pages/restaurant/RestaurantStoreCreditsPage";
import RestaurantStoreOrdersPage from "@/pages/restaurant/RestaurantStoreOrdersPage";
import RestaurantStoreStockPage from "@/pages/restaurant/RestaurantStoreStockPage";
import BranchStaffRequestsPage from "@/pages/restaurant/BranchStaffRequestsPage";
import BrandStaffRequestsPage from "@/pages/restaurant/BrandStaffRequestsPage";
import CounterDevicePage from "@/pages/devices/CounterDevicePage";
import DevicePairingPage from "@/pages/devices/DevicePairingPage";
import DevicesPage from "@/pages/devices/DevicesPage";
import { useEffect } from "react";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } }
});

export default function App(): JSX.Element {
  useEffect(() => {
    initAutoSync();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/device/pair" element={<DevicePairingPage />} />
          <Route element={<DeviceProtectedRoute type="counter" />}>
            <Route path="/counter" element={<CounterDevicePage />} />
            <Route element={<ProtectedRoute permission="fb.order.create" />}>
              <Route path="/counter/orders" element={<WapOrderPage />} />
            </Route>
          </Route>
          <Route element={<DeviceProtectedRoute type="kitchen" />}>
            <Route path="/kitchen" element={<KitchenDisplayPage />} />
          </Route>
          <Route element={<DeviceProtectedRoute type="pickup" />}>
            <Route path="/pickup" element={<PickupDisplayPage />} />
          </Route>
          <Route path="/accept-invitation" element={<AcceptInvitationPage />} />
          <Route path="/" element={Capacitor.isNativePlatform() ? <Navigate to="/restaurant" replace /> : <ModuleSelectorPage />} />
          <Route path="/store" element={<StorefrontPage />} />
          <Route path="/erp" element={<Navigate to="/admin" replace />} />
          <Route element={<ProtectedRoute permission="pos.sale.create" />}>
            <Route path="/pos" element={<POSPage />} />
          </Route>
          <Route element={<ProtectedRoute permissions={["brand.store.order.create", "brand.store.shift.close", "brand.store.replenishment.submit", "brand.store.delivery.receive", "brand.store.stock.view", "brand.store.stock.adjust", "fb.order.create", "system.user.request"]} />}>
            <Route element={<RestaurantShell />}>
              <Route element={<ProtectedRoute permissions={["brand.store.order.create", "fb.order.create"]} />}>
                <Route path="/store/:brandSlug/orders" element={<WapOrderPage />} />
              </Route>
              <Route element={<ProtectedRoute permissions={["brand.store.shift.close", "fb.order.create"]} />}>
                <Route path="/store/:brandSlug/close-shift" element={<WapShiftClosePage />} />
              </Route>
              <Route element={<ProtectedRoute permissions={["brand.store.stock.view", "brand.store.stock.adjust"]} />}>
                <Route path="/store/:brandSlug/stock" element={<RestaurantStoreStockPage />} />
              </Route>
              <Route element={<ProtectedRoute permissions={["brand.store.replenishment.submit", "brand.store.delivery.receive", "fb.order.create"]} />}>
                <Route path="/store/:brandSlug/replenishment-orders" element={<RestaurantStoreOrdersPage />} />
                <Route path="/store/:brandSlug/credits" element={<RestaurantStoreCreditsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="system.user.request" />}>
                <Route path="/store/:brandSlug/staff" element={<BranchStaffRequestsPage />} />
                <Route path="/store/:brandSlug/branches/:branchCode/staff" element={<BranchStaffRequestsPage />} />
              </Route>
            </Route>
          </Route>
          <Route element={<ProtectedRoute permissions={[
            "brand.central.raw_stock.view",
            "brand.central.raw_stock.manage",
            "brand.central.ready_stock.view",
            "brand.central.ready_stock.manage",
            "brand.central.production.view",
            "brand.central.production.manage",
            "fb.kitchen.manage",
            "fb.recipe.manage",
            "fb.report.view",
            "system.user.approve"
          ]} />}>
            <Route element={<RestaurantShell />}>
              <Route element={<ProtectedRoute permission="fb.kitchen.manage" />}>
                <Route path="/central/:brandSlug/orders" element={<RestaurantCentralOrdersPage />} />
              </Route>
              <Route element={<ProtectedRoute permissions={[
                "brand.central.production.view",
                "brand.central.production.manage",
                "fb.kitchen.manage"
              ]} />}>
                <Route path="/central/:brandSlug/production" element={<RestaurantCentralProductionPage />} />
              </Route>
              <Route element={<ProtectedRoute permissions={[
                "brand.central.raw_stock.view",
                "brand.central.raw_stock.manage",
                "brand.central.ready_stock.view",
                "brand.central.ready_stock.manage",
                "brand.central.production.view",
                "brand.central.production.manage",
                "fb.kitchen.manage"
              ]} />}>
                <Route path="/central/:brandSlug/stock" element={<RestaurantCentralStockPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="fb.kitchen.manage" />}>
                <Route path="/central/:brandSlug/credits" element={<RestaurantCentralCreditsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="fb.report.view" />}>
                <Route path="/central/:brandSlug/reports" element={<RestaurantCentralReportsPage />} />
              </Route>
              <Route element={<ProtectedRoute permissions={[
                "brand.central.raw_stock.view",
                "brand.central.raw_stock.manage",
                "brand.central.ready_stock.view",
                "brand.central.ready_stock.manage",
                "fb.kitchen.manage"
              ]} />}>
                <Route path="/central/:brandSlug/cutover" element={<RestaurantStockCutoverPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="fb.recipe.manage" />}>
                <Route path="/central/:brandSlug/recipes" element={<RecipesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="system.user.approve" />}>
                <Route path="/central/:brandSlug/staff" element={<BrandStaffRequestsPage />} />
              </Route>
            </Route>
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/admin" element={<DashboardPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route element={<ProtectedRoute permission="system.user.view" />}>
                <Route path="/users" element={<UsersPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="system.role.view" />}>
                <Route path="/roles" element={<RolesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="system.branch.view" />}>
                <Route path="/branches" element={<BranchesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="system.device.view" />}>
                <Route path="/devices" element={<DevicesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="accounting.report.view" />}>
                <Route path="/accounting" element={<AccountingPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="accounting.payment.view" />}>
                <Route path="/payable" element={<PayablePage />} />
              </Route>
              <Route element={<ProtectedRoute permission="accounting.invoice.view" />}>
                <Route path="/etax" element={<ETaxPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="hr.employee.view" />}>
                <Route path="/hr" element={<HRPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="system.company.edit" />}>
                <Route path="/integrations" element={<IntegrationsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="pos.sale.view" />}>
                <Route path="/crm" element={<CRMPage />} />
                <Route path="/logistics" element={<ShipmentsPage />} />
              </Route>
              <Route path="/branches/:id/settings" element={<BranchSettingsPage />} />
              <Route element={<ProtectedRoute permission="inventory.product.view" />}>
                <Route path="/products" element={<ProductsPage />} />
                <Route path="/products/new" element={<ProductFormPage />} />
                <Route path="/products/:id/edit" element={<ProductFormPage />} />
                <Route path="/units" element={<UnitsPage />} />
              </Route>
              <Route element={<ProtectedRoute permissions={["inventory.stock.view", "inventory.stock.adjust.request"]} />}>
                <Route path="/stock" element={<StockPage />} />
                <Route path="/stock/multi-branch" element={<MultiBranchStockPage />} />
                <Route path="/stock-count" element={<StockCountPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="inventory.stock.adjust" />}>
                <Route path="/stock-count/:id" element={<CountingPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="inventory.transfer.view" />}>
                <Route path="/transfer/orders" element={<TransferOrdersPage />} />
                <Route path="/transfer/orders/:id" element={<TOFormPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="inventory.transfer.create" />}>
                <Route path="/transfer/orders/new" element={<TOFormPage />} />
              </Route>
              <Route element={<ProtectedRoute permissions={["pos.sale.view", "pos.sale.create", "pos.report.view", "system.company.edit"]} />}>
                <Route path="/pos/admin" element={<POSAdminPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="pos.report.view" />}>
                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/shift-history" element={<ShiftHistoryPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="inventory.purchase.view" />}>
                <Route path="/purchase/suppliers" element={<SuppliersPage />} />
                <Route path="/purchase/orders" element={<PurchaseOrdersPage />} />
                <Route path="/purchase/orders/:id" element={<POFormPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="inventory.purchase.create" />}>
                <Route path="/purchase/orders/new" element={<POFormPage />} />
              </Route>
              <Route path="/403" element={<NotFoundPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
          {/* F&B Module */}
          {/* Public routes — no login required */}
          <Route path="/menu/:token" element={<CustomerMenuPage />} />
          <Route path="/order/:token" element={<QuickServicePage />} />
          {/* F&B setup wizard — no AppShell */}
          <Route element={<ProtectedRoute permission="fb.settings.manage" />}>
            <Route path="/restaurant/setup" element={<FBSetupWizard />} />
          </Route>
          {/* Kitchen & Pickup — fullscreen, no AppShell */}
          <Route element={<ProtectedRoute permissions={["fb.kitchen.ticket.manage", "fb.kitchen.manage"]} />}>
            <Route path="/restaurant/kitchen" element={<KitchenDisplayPage />} />
          </Route>
          <Route element={<ProtectedRoute permission="fb.kitchen.manage" />}>
            <Route path="/restaurant/pickup" element={<PickupDisplayPage />} />
          </Route>
          <Route element={<ProtectedRoute permissions={["fb.menu.view", "fb.table.manage", "fb.order.create", "fb.kitchen.ticket.manage", "fb.kitchen.manage", "fb.recipe.manage", "fb.report.view", "fb.settings.manage"]} />}>
            <Route element={<AppShell workspace="restaurant" />}>
              <Route path="/restaurant" element={<RestaurantIndexPage />} />
              <Route path="/restaurant/admin" element={<RestaurantAdminPage />} />
              <Route element={<ProtectedRoute permission="fb.table.manage" />}>
                <Route path="/restaurant/tables" element={<TableMapPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="fb.order.create" />}>
                <Route path="/restaurant/wap" element={<WapOrderPage />} />
                <Route path="/restaurant/close-shift" element={<WapShiftClosePage />} />
                <Route path="/restaurant/orders" element={<FBOrdersPage />} />
                <Route path="/restaurant/session/:sessionId/checkout" element={<SessionCheckoutPage />} />
                <Route path="/restaurant/session/:sessionId/detail" element={<SessionDetailPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="fb.recipe.manage" />}>
                <Route path="/restaurant/recipes" element={<RecipesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="fb.settings.manage" />}>
                <Route path="/restaurant/brands" element={<BrandAdminPage />} />
                <Route path="/restaurant/qr" element={<QRManagerPage />} />
                <Route path="/restaurant/settings" element={<FBSettingsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="fb.report.view" />}>
                <Route path="/restaurant/reports/ingredients" element={<IngredientReportPage />} />
              </Route>
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster />
    </QueryClientProvider>
  );
}
