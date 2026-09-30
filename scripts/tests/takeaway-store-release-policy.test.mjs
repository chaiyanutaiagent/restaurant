import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, sign, createHash } from "node:crypto";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { canonicalReleasePayload, validReleaseManifest, validReleaseUrl } from "../../frontend/src/mobile-store/releasePolicy.js";

const fixture = { surface: "takeaway_store", channel: "uat", package_id: "com.foodchainservice.takeaway.uat",
  version_name: "1.1.0-uat.fixture", version_code: 10106, minimum_supported_version_code: 10106,
  rollback_version_code: 10105, apk_url: "https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/fixture.apk",
  apk_sha256: "a".repeat(64), published_at: "2026-09-30T00:00:00.000Z", signature: "A".repeat(86) + "==" };

test("version and tenant-free manifest contract fails closed", () => {
  assert.equal(validReleaseManifest(fixture), true);
  assert.equal(validReleaseManifest({ ...fixture, rollback_version_code: null }), true);
  for (const patch of [
    { channel: "production" }, { package_id: "com.foodchainservice.takeaway" }, { channel: "__proto__" },
    { version_code: 0 }, { version_code: 2100000001 }, { version_code: 1.5 },
    { minimum_supported_version_code: 10107 }, { minimum_supported_version_code: 0 },
    { rollback_version_code: -1 }, { rollback_version_code: 0 }, { rollback_version_code: 10106 },
    { rollback_version_code: 10107 }, { rollback_version_code: 1.2 }, { rollback_version_code: "10105" },
    { company_id: "another-company" }, { business_code: "another-company" },
    { surface: "takeaway_admin" }, { signature: "" }, { version_name: " " }, { published_at: "invalid" },
  ]) assert.equal(validReleaseManifest({ ...fixture, ...patch }), false, JSON.stringify(patch));
  const prod = { ...fixture, channel: "production", package_id: "com.foodchainservice.takeaway",
    apk_url: "https://downloads.foodchainservice.com/downloads/takeaway-store/fixture.apk" };
  assert.equal(validReleaseManifest(prod), true);
});

test("update destinations never cross channels or carry credentials", () => {
  for (const value of [
    "http://uat-takeaway.foodchainservice.com/downloads/takeaway-store/fixture.apk",
    "https://downloads.foodchainservice.com/downloads/takeaway-store/fixture.apk",
    "https://uat-takeaway.foodchainservice.com.evil.test/downloads/takeaway-store/fixture.apk",
    fixture.apk_url.replace("https://", "https://user:pass@"),
    fixture.apk_url.replace(".com/", ".com:444/"), fixture.apk_url + "#fragment", fixture.apk_url + "?token=secret",
    fixture.apk_url.replace("fixture.apk", "../fixture.apk"), fixture.apk_url.replace("fixture.apk", "%2e%2e/fixture.apk"),
  ]) assert.equal(validReleaseUrl(value, "uat"), false, value);
});

test("release CLI validates signature hash channel and rollback even for signed invalid manifests", () => {
  const directory = mkdtempSync(join(tmpdir(), "store-release-fixture-"));
  try {
    const keys = generateKeyPairSync("ed25519");
    const apk = join(directory, "fixture.apk"), pub = join(directory, "public.pem"), priv = join(directory, "private.pem");
    const manifest = join(directory, "latest.json");
    writeFileSync(apk, "not a deployable APK: unit test fixture");
    writeFileSync(pub, keys.publicKey.export({ type: "spki", format: "pem" }));
    writeFileSync(priv, keys.privateKey.export({ type: "pkcs8", format: "pem" }), { mode: 0o600 });
    const run = (script, args) => spawnSync(process.execPath, [new URL(`../${script}`, import.meta.url).pathname, ...args], { encoding: "utf8" });
    const args = [apk, fixture.version_name, "10106", fixture.apk_url, "uat", fixture.package_id, priv, manifest, "10106", "10105"];
    assert.equal(run("create-takeaway-store-release-manifest.mjs", args).status, 0);
    const verify = () => run("verify-takeaway-store-release-manifest.mjs", [manifest, pub, apk, fixture.package_id, "uat"]);
    assert.equal(verify().status, 0);
    const valid = JSON.parse(readFileSync(manifest));
    assert.equal(valid.apk_sha256, createHash("sha256").update(readFileSync(apk)).digest("hex"));
    for (const patch of [{ rollback_version_code: 10106 }, { minimum_supported_version_code: 10107 },
      { channel: "production" }, { company_id: "company-two" }]) {
      const bad = { ...valid, ...patch };
      bad.signature = sign(null, Buffer.from(canonicalReleasePayload(bad)), keys.privateKey).toString("base64");
      writeFileSync(manifest, JSON.stringify(bad));
      assert.notEqual(verify().status, 0);
    }
    writeFileSync(manifest, JSON.stringify({ ...valid, apk_sha256: "b".repeat(64) }));
    assert.notEqual(verify().status, 0);
    writeFileSync(manifest, JSON.stringify({ ...valid, version_name: "tampered" }));
    assert.notEqual(verify().status, 0);
    const crossChannel = [...args]; crossChannel[4] = "production";
    assert.notEqual(run("create-takeaway-store-release-manifest.mjs", crossChannel).status, 0);
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
