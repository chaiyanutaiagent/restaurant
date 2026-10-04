import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
const root = path.resolve(process.argv[2] || "frontend/dist-mobile-store");
async function files(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  return (await Promise.all(entries.map((entry) => entry.isDirectory() ? files(path.join(dir, entry.name)) : [path.join(dir, entry.name)]))).flat();
}
const sources = (await files(root)).filter((name) => /\.(js|html|json)$/.test(name));
if (!sources.length) throw new Error("No compiled Store bundle");
const forbidden = ["/restaurant", "/retail", "/platform", "/takeaway/central", "/takeaway/admin", "/auth/uat/auto-login", "1b8a1818-44d6-4d5f-9d22-e5e17b23c081", "sketch-biz"];
for (const file of sources) {
  const content = await readFile(file, "utf8");
  for (const marker of forbidden) if (content.includes(marker)) throw new Error(`${file}: forbidden ${marker}`);
}
console.log(`PASS: ${sources.length} compiled files contain no forbidden routes, auto-login or default tenant`);
