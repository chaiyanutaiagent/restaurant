#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { createHash, verify } from "node:crypto";

const [manifestPath, publicKeyPath, apkPath, expectedPackage, expectedChannel] = process.argv.slice(2);
if (!manifestPath || !publicKeyPath || !apkPath || !expectedPackage || !expectedChannel) {
  throw new Error("usage: verify-takeaway-store-release-manifest <manifest-json> <ed25519-public-key> <apk> <package-id> <uat|production>");
}
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
if (manifest.surface !== "takeaway_store") throw new Error("unexpected surface");
if (manifest.package_id !== expectedPackage) throw new Error("unexpected package id");
if (manifest.channel !== expectedChannel) throw new Error("unexpected channel");
const digest = createHash("sha256").update(readFileSync(apkPath)).digest("hex");
if (digest !== manifest.apk_sha256) throw new Error("APK checksum mismatch");
const payload = {
  apk_sha256: manifest.apk_sha256,
  apk_url: manifest.apk_url,
  channel: manifest.channel,
  minimum_supported_version_code: manifest.minimum_supported_version_code,
  package_id: manifest.package_id,
  published_at: manifest.published_at,
  rollback_version_code: manifest.rollback_version_code,
  surface: manifest.surface,
  version_code: manifest.version_code,
  version_name: manifest.version_name,
};
if (!verify(null, Buffer.from(JSON.stringify(payload)), readFileSync(publicKeyPath), Buffer.from(manifest.signature, "base64"))) {
  throw new Error("release signature mismatch");
}
process.stdout.write(`verified ${manifest.surface} ${manifest.package_id} ${manifest.version_name} sha256=${digest}\n`);
