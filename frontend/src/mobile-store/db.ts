import Dexie, { type Table } from "dexie";
import type { TakeawayPendingSale, TakeawayWorkspaceSnapshot } from "../lib/db";
export type { TakeawayPendingSale, TakeawayWorkspaceSnapshot, TakeawayLocalOrder } from "../lib/db";

class StoreDatabase extends Dexie {
  takeawayWorkspaceSnapshots!: Table<TakeawayWorkspaceSnapshot, string>;
  takeawayPendingSales!: Table<TakeawayPendingSale, string>;
  offlineSettings!: Table<{ key: string; value: string }, string>;
  constructor() {
    super("foodchainservice-store-v1");
    this.version(1).stores({
      takeawayWorkspaceSnapshots: "key, company_id, branch_id, user_id",
      takeawayPendingSales: "client_sale_id, company_id, branch_id, user_id, status",
      offlineSettings: "key",
    });
  }
}
export const db = new StoreDatabase();

export async function cleanupStoreData(): Promise<void> {
  const unsynced = await db.takeawayPendingSales.filter((row) => row.status !== "synced").count();
  if (unsynced) throw new Error("มีรายการค้างส่งในเครื่อง กรุณาซิงก์ให้ครบก่อนออกจากระบบหรือเปลี่ยนบริษัท");
  await db.transaction("rw", db.takeawayWorkspaceSnapshots, db.takeawayPendingSales, async () => {
    await db.takeawayWorkspaceSnapshots.clear();
    await db.takeawayPendingSales.clear();
  });
}
