import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
const apk = process.argv[2];
if (!apk) throw new Error("Usage: node scripts/check-mobile-store-apk.mjs <candidate.apk>");
const entries = execFileSync("unzip", ["-Z1", apk], { encoding: "utf8" }).trim().split("\n");
const config = JSON.parse(execFileSync("unzip", ["-p", apk, "assets/capacitor.config.json"], { encoding: "utf8" }));
if (config.webDir !== "dist-mobile-store" || config.server.cleartext !== false || config.android.allowMixedContent !== false) throw new Error("Not an HTTPS Store bundle");
const assets = entries.filter((entry) => entry.startsWith("assets/public/") && /\.(js|html)$/.test(entry));
if (!assets.length) throw new Error("No Store assets");
for (const entry of assets) {
  const content = execFileSync("unzip", ["-p", apk, entry], { encoding: "utf8", maxBuffer: 10 * 1024 * 1024 });
  for (const marker of ["/restaurant", "/retail", "/platform", "/takeaway/central", "/takeaway/admin", "/auth/uat/auto-login", "1b8a1818-44d6-4d5f-9d22-e5e17b23c081", "sketch-biz"]) {
    if (content.includes(marker)) throw new Error(`${entry}: forbidden marker ${marker}`);
  }
}
console.log(JSON.stringify({ result: "PASS", apk, assets_checked: assets.length, sha256: createHash("sha256").update(readFileSync(apk)).digest("hex") }, null, 2));
