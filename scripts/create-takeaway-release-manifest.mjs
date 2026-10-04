#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { createHash, sign } from "node:crypto";

const [apkPath, versionName, versionCodeRaw, apkUrl, channel, privateKeyPath, outputPath, minimumRaw, rollbackRaw] = process.argv.slice(2);
if (!apkPath || !versionName || !versionCodeRaw || !apkUrl || !channel || !privateKeyPath || !outputPath) {
  throw new Error("usage: create-takeaway-release-manifest <apk> <version-name> <version-code> <apk-url> <uat|production> <ed25519-private-key> <output-json> [minimum-version-code] [rollback-version-code]");
}
if (!new Set(["uat", "production"]).has(channel)) throw new Error("channel must be uat or production");
const versionCode = Number(versionCodeRaw);
const minimumSupportedVersionCode = Number(minimumRaw || versionCodeRaw);
const rollbackVersionCode = rollbackRaw ? Number(rollbackRaw) : null;
if (![versionCode, minimumSupportedVersionCode].every(Number.isSafeInteger)) throw new Error("version codes must be integers");
const apkSha256 = createHash("sha256").update(readFileSync(apkPath)).digest("hex");
const payload = {
  apk_sha256: apkSha256,
  apk_url: apkUrl,
  channel,
  minimum_supported_version_code: minimumSupportedVersionCode,
  package_id: "com.foodchainservice.takeaway",
  published_at: new Date().toISOString(),
  rollback_version_code: rollbackVersionCode,
  version_code: versionCode,
  version_name: versionName,
};
const signature = sign(null, Buffer.from(JSON.stringify(payload)), readFileSync(privateKeyPath)).toString("base64");
writeFileSync(outputPath, `${JSON.stringify({
  channel: payload.channel,
  package_id: payload.package_id,
  version_name: payload.version_name,
  version_code: payload.version_code,
  minimum_supported_version_code: payload.minimum_supported_version_code,
  rollback_version_code: payload.rollback_version_code,
  apk_url: payload.apk_url,
  apk_sha256: payload.apk_sha256,
  published_at: payload.published_at,
  signature,
}, null, 2)}\n`, { mode: 0o644 });
