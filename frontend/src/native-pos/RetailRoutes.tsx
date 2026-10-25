import { Route } from "react-router-dom";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import POSPage from "@/pages/pos/POSPage";
import RetailSkuReportPage from "@/pages/reports/RetailSkuReportPage";
import OfflineSyncCenterPage from "@/pages/pos/OfflineSyncCenterPage";
import CRMPage from '@/pages/crm/CRMPage';
import { RetailWorkspaceFrame } from '@/components/pos/RetailWorkspaceNav';
import { RetailManagementPage, RetailWorkspacePage } from '@/components/pos/RetailWorkspaceHub';

export const productRoutes = <>
  <Route element={<ProtectedRoute/>}><Route path="/retail/workspace/:section" element={<RetailWorkspacePage/>}/></Route>
  <Route element={<ProtectedRoute permission="pos.sale.create"/>}>
    <Route path="/retail/pos" element={<POSPage/>}/>
    <Route path="/retail/offline-sync" element={<RetailWorkspaceFrame section="settings"><OfflineSyncCenterPage/></RetailWorkspaceFrame>}/>
  </Route>
  <Route element={<ProtectedRoute permission="inventory.product.create"/>}><Route path="/retail/products/scan" element={<RetailManagementPage task="intake"/>}/></Route>
  <Route element={<ProtectedRoute permission="inventory.transfer.view"/>}><Route path="/retail/transfers" element={<RetailManagementPage task="transfer"/>}/></Route>
  <Route element={<ProtectedRoute permission="pos.report.view"/>}><Route path="/retail/reports/skus" element={<RetailWorkspaceFrame section="reports"><RetailSkuReportPage/></RetailWorkspaceFrame>}/></Route>
  <Route element={<ProtectedRoute permission="pos.sale.view"/>}><Route path="/crm" element={<RetailWorkspaceFrame section="bills"><CRMPage/></RetailWorkspaceFrame>}/></Route>
</>;
