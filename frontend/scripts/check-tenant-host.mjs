import { build } from "esbuild";
import assert from "node:assert/strict";

const compiled = await build({
  entryPoints: ["src/config/productRouting.ts"], bundle: true, write: false,
  format: "esm", platform: "node",
});
const routing = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);
for (const workspace of ["company", "restaurant", "retail", "takeaway"]) {
  const url = routing.workspaceUrl(workspace, undefined, {
    hostname: "sketchbiz.foodchainservice.com", protocol: "https:",
  });
  assert.equal(new URL(url).hostname, "sketchbiz.foodchainservice.com");
}
assert.equal(routing.workspaceFromHostname("sketchbiz.foodchainservice.com"), null);
assert.equal(routing.workspaceHost("retail", "uat-app.foodchainservice.com"), "uat-retail.foodchainservice.com");
assert.equal(routing.workspaceHost("retail", "app.foodchainservice.com"), "retail.foodchainservice.com");
console.log("Tenant routing: 7 checks passed");
