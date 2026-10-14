import { Route } from "react-router-dom";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import POSPage from "@/pages/pos/POSPage";
import RetailProductIntakePage from "@/pages/products/RetailProductIntakePage";
import RetailTransfersPage from "@/pages/stock/RetailTransfersPage";
import RetailSkuReportPage from "@/pages/reports/RetailSkuReportPage";
import OfflineSyncCenterPage from "@/pages/pos/OfflineSyncCenterPage";
import CRMPage from '@/pages/crm/CRMPage';

export const productRoutes = <>
  <Route element={<ProtectedRoute permission="pos.sale.create"/>}>
    <Route path="/retail/pos" element={<POSPage/>}/>
    <Route path="/retail/offline-sync" element={<OfflineSyncCenterPage/>}/>
  </Route>
  <Route element={<ProtectedRoute permission="inventory.product.create"/>}><Route path="/retail/products/scan" element={<RetailProductIntakePage/>}/></Route>
  <Route element={<ProtectedRoute permission="inventory.transfer.view"/>}><Route path="/retail/transfers" element={<RetailTransfersPage/>}/></Route>
  <Route element={<ProtectedRoute permission="pos.report.view"/>}><Route path="/retail/reports/skus" element={<RetailSkuReportPage/>}/></Route>
  <Route element={<ProtectedRoute permission="pos.sale.view"/>}><Route path="/crm" element={<CRMPage/>}/></Route>
</>;
