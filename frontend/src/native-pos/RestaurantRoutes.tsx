import { Navigate, Route } from "react-router-dom";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import POSPage from "@/pages/pos/POSPage";
import TableMapPage from "@/pages/restaurant/TableMapPage";
import KitchenDisplayPage from "@/pages/restaurant/KitchenDisplayPage";
import FBOrdersPage from "@/pages/restaurant/FBOrdersPage";
import SessionCheckoutPage from "@/pages/restaurant/SessionCheckoutPage";
import SessionDetailPage from "@/pages/restaurant/SessionDetailPage";
import QRManagerPage from "@/pages/restaurant/QRManagerPage";
import OfflineSyncCenterPage from "@/pages/pos/OfflineSyncCenterPage";
import CRMPage from '@/pages/crm/CRMPage';
import WapOrderPage from '@/pages/restaurant/WapOrderPage';
import WapShiftClosePage from '@/pages/restaurant/WapShiftClosePage';
import PickupDisplayPage from '@/pages/restaurant/PickupDisplayPage';

export const productRoutes = <>
  <Route element={<ProtectedRoute permission="pos.sale.create"/>}>
    <Route path="/restaurant/pos" element={<POSPage/>}/>
    <Route path="/restaurant/offline-sync" element={<OfflineSyncCenterPage/>}/>
    <Route path="/restaurant/wap" element={<Navigate to="/restaurant/pos?channel=takeaway" replace/>}/>
  </Route>
  <Route element={<ProtectedRoute permission="fb.table.manage"/>}><Route path="/restaurant/tables" element={<TableMapPage/>}/></Route>
  <Route element={<ProtectedRoute permission="fb.order.create"/>}>
    <Route path="/restaurant/wap/legacy" element={<WapOrderPage/>}/>
    <Route path="/restaurant/close-shift" element={<WapShiftClosePage/>}/>
    <Route path="/restaurant/orders" element={<FBOrdersPage/>}/>
    <Route path="/restaurant/session/:sessionId/checkout" element={<SessionCheckoutPage/>}/>
    <Route path="/restaurant/session/:sessionId/detail" element={<SessionDetailPage/>}/>
  </Route>
  <Route element={<ProtectedRoute permissions={["fb.kitchen.ticket.manage","fb.kitchen.manage"]}/>}><Route path="/restaurant/kitchen" element={<KitchenDisplayPage/>}/></Route>
  <Route element={<ProtectedRoute permission="fb.settings.manage"/>}><Route path="/restaurant/qr" element={<QRManagerPage/>}/></Route>
  <Route element={<ProtectedRoute permission="fb.kitchen.manage"/>}><Route path="/restaurant/pickup" element={<PickupDisplayPage/>}/></Route>
  <Route element={<ProtectedRoute permission="pos.sale.view"/>}><Route path="/crm" element={<CRMPage/>}/></Route>
</>;
