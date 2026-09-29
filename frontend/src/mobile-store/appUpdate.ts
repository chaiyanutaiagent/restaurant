import type { TakeawayReleaseManifest } from "../lib/takeawayAppUpdate";

// The legacy channel identifies the full app, not this restricted Store surface.
// Keep candidate installation manual until QA approves a Store-specific channel.
export async function loadTakeawayRelease(): Promise<{ manifest: TakeawayReleaseManifest; verified: boolean }> {
  throw new Error("Store UAT updates are distributed manually by QA; legacy update channel is disabled");
}
