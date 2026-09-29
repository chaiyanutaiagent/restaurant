#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { createHash, sign } from "node:crypto";

const [apkPath, versionName, versionCodeRaw, apkUrl, channel, packageId, privateKeyPath, outputPath, minimumRaw, rollbackRaw] = process.argv.slice(2);
if (!apkPath || !versionName || !versionCodeRaw || !apkUrl || !channel || !packageId || !privateKeyPath || !outputPath) {
  throw new Error("usage: create-takeaway-store-release-manifest <apk> <version-name> <version-code> <apk-url> <uat|production> <package-id> <ed25519-private-key> <output-json> [minimum-version-code] [rollback-version-code]");
}
if (!new Set(["uat", "production"]).has(channel)) throw new Error("channel must be uat or production");
if (!/^com\.foodchainservice\.takeaway(?:\.uat)?$/.test(packageId)) throw new Error("unexpected package id");
if (!/^https:\/\//.test(apkUrl)) throw new Error("apk url must use HTTPS");
const versionCode = Number(versionCodeRaw);
const minimumSupportedVersionCode = Number(minimumRaw || versionCodeRaw);
const rollbackVersionCode = rollbackRaw ? Number(rollbackRaw) : null;
if (![versionCode, minimumSupportedVersionCode].every(Number.isSafeInteger)
    || (rollbackVersionCode !== null && !Number.isSafeInteger(rollbackVersionCode))) {
  throw new Error("version codes must be integers");
}
if (versionCode < 1 || minimumSupportedVersionCode < 1 || minimumSupportedVersionCode > versionCode) {
  throw new Error("minimum version code must be positive and no greater than release version code");
}
if (rollbackVersionCode !== null && (rollbackVersionCode < 1 || rollbackVersionCode >= versionCode)) {
  throw new Error("rollback version code must be positive and lower than release version code");
}
const payload = {
  apk_sha256: createHash("sha256").update(readFileSync(apkPath)).digest("hex"),
  apk_url: apkUrl,
  channel,
  minimum_supported_version_code: minimumSupportedVersionCode,
  package_id: packageId,
  published_at: new Date().toISOString(),
  rollback_version_code: rollbackVersionCode,
  surface: "takeaway_store",
  version_code: versionCode,
  version_name: versionName,
};
const signature = sign(null, Buffer.from(JSON.stringify(payload)), readFileSync(privateKeyPath)).toString("base64");
writeFileSync(outputPath, `${JSON.stringify({
  surface: payload.surface,
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
