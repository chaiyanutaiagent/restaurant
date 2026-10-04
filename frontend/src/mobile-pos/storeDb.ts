import { db } from "../lib/db";
export { db };
export type * from "../lib/db";

export async function assertNoPendingData(): Promise<void> {
  const [takeaway, retail, restaurant, holds, transactions] = await Promise.all([
    db.takeawayPendingSales.toArray(), db.pendingSales.toArray(), db.restaurantPendingOrders.toArray(),
    db.heldBills.toArray(), db.pendingTransactions.toArray(),
  ]);
  if (takeaway.some((row) => row.status !== "synced") || retail.some((row) => !row.synced)
      || restaurant.some((row) => !["reconciled", "rejected"].includes(row.status))
      || holds.some((row) => row.sync_state !== "synced") || transactions.some((row) => !row.syncedAt)) {
    throw new Error("มีรายการค้างส่งหรือพักบิลในเครื่อง กรุณาซิงก์ให้ครบก่อนออกจากระบบหรือเปลี่ยนบริษัท");
  }
}
export async function cleanupStoreData(): Promise<void> {
  await assertNoPendingData();
  await db.transaction("rw", db.tables, async () => { for (const table of db.tables) await table.clear(); });
  localStorage.removeItem("restaurant-pos-current-shift");
  localStorage.removeItem("pos-catalog-isolation-key");
}
