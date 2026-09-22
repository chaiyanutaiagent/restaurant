from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WP58RetailOfflineReadinessTests(unittest.TestCase):
    def test_retail_offline_payment_remains_fail_closed(self) -> None:
        center = (ROOT / "frontend/src/pages/pos/RetailOfflineSyncCenterPage.tsx").read_text()
        sync = (ROOT / "frontend/src/lib/syncService.ts").read_text()

        self.assertIn("Retail POS ยังไม่อนุญาตให้รับชำระออฟไลน์", center)
        self.assertIn('scope.businessType === "retail_pos"', sync)
        self.assertIn('last_error_code: "retail_offline_not_authorized"', sync)
        self.assertNotIn("posApi.syncSales(ordersPayload)", sync.split('if (scope.businessType === "retail_pos")', 1)[1].split("let synced", 1)[0])

    def test_pending_sales_are_isolated_by_signed_context(self) -> None:
        sync = (ROOT / "frontend/src/lib/syncService.ts").read_text()
        center = (ROOT / "frontend/src/pages/pos/RetailOfflineSyncCenterPage.tsx").read_text()
        db = (ROOT / "frontend/src/lib/db.ts").read_text()

        for clause in (
            "item.company_id === scope.companyId",
            "item.branch_id === scope.branchId",
            "item.user_id === scope.userId",
            "item.business_type === scope.businessType",
        ):
            self.assertIn(clause, sync)
        self.assertIn('.where("[company_id+branch_id+business_type]")', center)
        self.assertIn('.equals([companyId, branchId, "retail_pos"])', center)
        self.assertIn("row.user_id === user.id", center)
        self.assertIn("กักข้อมูลเดิมที่ไม่มีบริบท", center)
        self.assertIn('row.last_error_code = "legacy_context_missing"', db)

    def test_online_listener_does_not_sync_without_context(self) -> None:
        sync = (ROOT / "frontend/src/lib/syncService.ts").read_text()
        listener = sync.split('window.addEventListener("online"', 1)[1].split("});", 1)[0]

        self.assertNotIn("syncPendingSales", listener)
        self.assertIn("syncProductCatalog", listener)
        self.assertIn("syncStockBalances", listener)

    def test_recovery_center_exposes_item_ack_and_safe_review_states(self) -> None:
        center = (ROOT / "frontend/src/pages/pos/RetailOfflineSyncCenterPage.tsx").read_text()
        sync = (ROOT / "frontend/src/lib/syncService.ts").read_text()
        schema = (ROOT / "backend/app/schemas/pos.py").read_text()

        for state in ("pending", "syncing", "needs_review", "synced"):
            self.assertIn(state, center)
        self.assertIn("ordersByClientId", sync)
        self.assertIn('last_error_code: "missing_item_acknowledgement"', sync)
        self.assertIn("client_order_id: str | None = None", schema)
        self.assertIn("ห้ามลบรายการรับเงินจริง", center)

    def test_retail_readiness_is_business_aware_and_hardware_stays_manual(self) -> None:
        service = (ROOT / "backend/app/services/physical_uat_service.py").read_text()
        page = (ROOT / "frontend/src/pages/devices/PhysicalUATReadinessPage.tsx").read_text()

        for check in (
            "retail_offline_blocked",
            "retail_non_cash_blocked",
            "retail_data_boundary",
            "product_barcode",
            "customer_receipt",
            "printer_recovery",
            "cash_drawer",
            "retail_cash_e2e",
            "network_before_submit",
            "lost_ack",
            "row_parity",
            "rollback_recovery",
        ):
            self.assertIn(f'("{check}"', service)
        self.assertIn("RETAIL_MANUAL_CHECKS", service)
        self.assertIn("self._business_type(session)", service)
        self.assertIn("Retail Cash Pilot", page)
        self.assertIn("ไม่ยืนยัน Printer/Drawer/Scanner จาก Browser", page)
        self.assertIn("ไม่เปลี่ยน Production Legacy source", page)


if __name__ == "__main__":
    unittest.main()
