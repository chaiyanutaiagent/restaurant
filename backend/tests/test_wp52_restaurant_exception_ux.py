from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WP52RestaurantExceptionUXTests(unittest.TestCase):
    def test_legacy_refund_client_paths_are_removed(self) -> None:
        pos_page = (ROOT / "frontend/src/pages/pos/POSPage.tsx").read_text()
        pos_api = (ROOT / "frontend/src/lib/posApi.ts").read_text()

        self.assertNotIn("posApi.refundSale", pos_page)
        self.assertNotIn("posApi.partialRefundSale", pos_page)
        self.assertNotIn("refundSale:", pos_api)
        self.assertNotIn("partialRefundSale:", pos_api)
        self.assertIn("RefundWorkspaceDialog", pos_page)

    def test_bill_center_routes_settled_payments_to_refund(self) -> None:
        center = (ROOT / "frontend/src/components/pos/BillReceiptCenterDialog.tsx").read_text()

        self.assertIn('["authorized", "pending"]', center)
        self.assertIn("ให้ใช้ Refund แทน", center)
        self.assertIn("แลกสินค้า · ยังไม่เปิดใช้", center)
        self.assertIn("disabled title=\"ยังไม่มี Atomic exchange contract\"", center)

    def test_refund_simulator_is_explicit_and_defaults_off_in_images(self) -> None:
        refund = (ROOT / "frontend/src/components/pos/RefundWorkspaceDialog.tsx").read_text()
        dockerfile = (ROOT / "frontend/Dockerfile").read_text()

        self.assertIn('VITE_REFUND_UAT_SIMULATOR === "true"', refund)
        self.assertIn("UAT_SIMULATOR_ENABLED ?", refund)
        self.assertIn("ARG VITE_REFUND_UAT_SIMULATOR=false", dockerfile)

    def test_cancellation_and_discount_surfaces_remain_server_authoritative(self) -> None:
        cancellation = (ROOT / "frontend/src/pages/restaurant/SessionDetailPage.tsx").read_text()
        discount = (ROOT / "frontend/src/components/pos/DiscountWorkspaceDialog.tsx").read_text()

        self.assertIn('authApi.post("/restaurant/cancellations/preview"', cancellation)
        self.assertIn('action="fb.order.cancel_after_kitchen"', cancellation)
        self.assertIn("Waste Ledger", cancellation)
        self.assertIn("ยอดสุดท้ายและสิทธิ์จะถูกตรวจซ้ำโดย Server", discount)
        self.assertIn("Structured discount reason ยังไม่มี", discount)

    def test_legacy_online_order_routes_cannot_bypass_offline_sync_authorization(self) -> None:
        restaurant_router = (ROOT / "backend/app/routers/restaurant.py").read_text()

        self.assertEqual(
            restaurant_router.count(
                "Offline orders must be submitted through the authorized sync endpoint"
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
