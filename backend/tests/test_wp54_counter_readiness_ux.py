from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WP54CounterReadinessUXTests(unittest.TestCase):
    def test_readiness_page_is_explicitly_uat_and_never_claims_production_ready(self) -> None:
        page = (ROOT / "frontend/src/pages/devices/PhysicalUATReadinessPage.tsx").read_text()

        self.assertIn("UAT ONLY", page)
        self.assertIn("ตรวจความพร้อมก่อนเปิดร้าน", page)
        self.assertIn("ไม่เปิด Production flag", page)
        self.assertNotIn("Production Ready", page)

    def test_automatic_and_physical_evidence_are_visually_distinct(self) -> None:
        page = (ROOT / "frontend/src/pages/devices/PhysicalUATReadinessPage.tsx").read_text()

        self.assertIn("ระบบตรวจ ณ เวลานี้", page)
        self.assertIn("ต้องทดสอบบนอุปกรณ์จริง", page)
        self.assertIn("ห้ามอนุมานจาก Browser", page)
        self.assertIn("ผ่านพร้อมหลักฐาน", page)
        self.assertIn("ยังไม่ยืนยัน", page)

    def test_na_is_only_offered_for_cash_drawer(self) -> None:
        page = (ROOT / "frontend/src/pages/devices/PhysicalUATReadinessPage.tsx").read_text()
        service = (ROOT / "backend/app/services/physical_uat_service.py").read_text()

        self.assertIn('const NA_ALLOWED_CHECKS = new Set(["cash_drawer"])', page)
        self.assertIn("NA_ALLOWED_CHECKS.has(check.check_key)", page)
        self.assertIn('NA_ALLOWED_CHECKS = {"cash_drawer"}', service)

    def test_gate_blocks_incomplete_or_critical_evidence(self) -> None:
        page = (ROOT / "frontend/src/pages/devices/PhysicalUATReadinessPage.tsx").read_text()
        service = (ROOT / "backend/app/services/physical_uat_service.py").read_text()

        self.assertIn("blockers.length === 0", page)
        self.assertIn("critical_defects", page)
        self.assertIn("รายการบังคับยังไม่ครบ", page)
        self.assertIn("uat_not_ready", service)
        self.assertIn("Maker and checker must be different users", service)
        self.assertIn("Technical and Business signers must be different users", service)

    def test_hardware_network_reconciliation_and_recovery_are_covered(self) -> None:
        service = (ROOT / "backend/app/services/physical_uat_service.py").read_text()

        for check in (
            "product_barcode",
            "table_qr",
            "customer_receipt",
            "kitchen_slip",
            "printer_recovery",
            "cash_drawer",
            "promptpay_sandbox",
            "dine_in_e2e",
            "takeaway_e2e",
            "offline_cash_reconnect",
            "lost_ack",
            "network_toggle",
            "row_parity",
            "rollback_recovery",
        ):
            self.assertIn(f'("{check}"', service)

    def test_evidence_secret_filter_remains_server_side(self) -> None:
        service = (ROOT / "backend/app/services/physical_uat_service.py").read_text()

        self.assertIn("SECRET_PATTERN", service)
        self.assertIn("Evidence contains a forbidden secret or credential", service)
        self.assertIn("Approved evidence is immutable", service)


if __name__ == "__main__":
    unittest.main()

