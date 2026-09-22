from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WP53OfflineSyncRecoveryUXTests(unittest.TestCase):
    def test_pos_has_a_protected_offline_sync_route(self) -> None:
        app = (ROOT / "frontend/src/App.tsx").read_text()
        pos_page = (ROOT / "frontend/src/pages/pos/POSPage.tsx").read_text()

        self.assertIn('path="/pos/offline-sync"', app)
        self.assertIn('openWorkspace("/pos/offline-sync", "ศูนย์ซิงก์รายการขาย")', pos_page)
        self.assertIn("takeawayOutboxSummary.acknowledged", pos_page)
        self.assertIn("takeawayOutboxSummary.unknown", pos_page)
        self.assertIn("takeawayOutboxSummary.quarantined", pos_page)

    def test_sync_center_reads_the_real_encrypted_outbox(self) -> None:
        page = (ROOT / "frontend/src/pages/pos/OfflineSyncCenterPage.tsx").read_text()

        self.assertIn('import { liveQuery } from "dexie"', page)
        self.assertIn("listRestaurantOutbox", page)
        self.assertIn("getRestaurantOutboxSummary", page)
        self.assertIn("getQueuedRestaurantOrder", page)
        self.assertIn("getCachedRestaurantMenu", page)
        self.assertIn("inquireRestaurantOperation", page)
        self.assertIn("syncRestaurantPendingOrders", page)

    def test_operator_language_does_not_overclaim_or_offer_deletion(self) -> None:
        page = (ROOT / "frontend/src/pages/pos/OfflineSyncCenterPage.tsx").read_text()

        self.assertIn("ออฟไลน์รับเฉพาะเงินสด", page)
        self.assertIn("Idempotency Key เดิม", page)
        self.assertIn("ตรวจสถานะเดิม", page)
        self.assertNotIn("ขายสำเร็จบน Server", page)
        self.assertNotIn("ลบจากคิว", page)

    def test_recovery_states_have_distinct_operator_actions(self) -> None:
        page = (ROOT / "frontend/src/pages/pos/OfflineSyncCenterPage.tsx").read_text()

        for state in (
            "pending_sync",
            "syncing",
            "server_acknowledged",
            "reconciled",
            "needs_review",
            "rejected",
            "quarantined",
            "unknown",
        ):
            self.assertIn(f"{state}:", page)
        self.assertIn('selectedRow.status === "unknown"', page)
        self.assertIn('selectedRow.status === "needs_review"', page)
        self.assertIn("เรียกผู้จัดการตรวจสอบ", page)

    def test_retry_remains_idempotent_and_unknown_is_inquired_first(self) -> None:
        offline = (ROOT / "frontend/src/lib/restaurantOffline.ts").read_text()

        self.assertIn("idempotency_key: `offline-sale:", offline)
        self.assertIn("await inquireUnknown(row)", offline)
        self.assertIn("ACTIVE_SYNC_STATES", offline)
        self.assertIn('status: "quarantined"', offline)


if __name__ == "__main__":
    unittest.main()
