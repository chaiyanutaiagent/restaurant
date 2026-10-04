import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(process.argv[2] || fileURLToPath(new URL("../frontend/dist-mobile-pos", import.meta.url)));
async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  return (await Promise.all(entries.map((entry) => entry.isDirectory() ? walk(path.join(dir, entry.name)) : path.join(dir, entry.name)))).flat();
}
const files = (await walk(root)).filter((file) => /\.(js|html|json)$/.test(file));
if (!files.length) throw new Error("Missing POS bundle");
const contents = await Promise.all(files.map((file) => readFile(file, "utf8")));
const bundle = contents.join("\n");
for (const marker of ["/platform/companies", "/takeaway/admin", "/takeaway/central",
  "/auth/uat/auto-login", "sketch-biz", "erp-auth\":", "TakeawayUpdater", "downloads/takeaway-store",
  "foodchainservice.store.session.v1", "MOBILE_POS_ENV_LEAK_FIXTURE", "1b8a1818-44d6-4d5f-9d22-e5e17b23c081"]) {
  if (bundle.includes(marker)) throw new Error(`POS boundary violation: ${marker}`);
}
for (const marker of ["https://uat-takeaway.foodchainservice.com", "https://uat-restaurant.foodchainservice.com", "https://uat-retail.foodchainservice.com", "foodchainservice.pos.uat", "FoodchainservicePOSUATDatabase"]) {
  if (!bundle.includes(marker)) throw new Error(`Missing POS isolation marker: ${marker}`);
}
if ((await walk(root)).some((file) => file.endsWith(".map"))) throw new Error("POS sourcemaps must not ship");
console.log(`PASS: POS UAT boundary, isolated storage, no legacy updater (${files.length} compiled files)`);
