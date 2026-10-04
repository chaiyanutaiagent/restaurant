// One wire-format policy for the browser and offline release tooling.
const packages = { uat: "com.foodchainservice.takeaway.uat", production: "com.foodchainservice.takeaway" };
const payloadKeys = ["apk_sha256", "apk_url", "channel", "minimum_supported_version_code",
  "package_id", "published_at", "rollback_version_code", "surface", "version_code", "version_name"];

export function validReleaseChannel(packageId, channel) {
  return Object.hasOwn(packages, channel) && packages[channel] === packageId;
}

export function validReleaseUrl(value, channel, extension = ".apk") {
  try {
    const url = new URL(value);
    const host = channel === "uat" ? "uat-takeaway.foodchainservice.com" : "downloads.foodchainservice.com";
    return (channel === "uat" || channel === "production") && url.protocol === "https:"
      && url.hostname === host && !url.username && !url.password && !url.port && !url.hash && !url.search
      && url.pathname.startsWith("/downloads/takeaway-store/") && url.pathname.endsWith(extension)
      && !url.pathname.includes("%");
  } catch { return false; }
}

export function validReleaseManifest(value, requireSignature = true) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const m = value;
  return Object.keys(m).every((key) => payloadKeys.includes(key) || key === "signature")
    && m.surface === "takeaway_store" && validReleaseChannel(m.package_id, m.channel)
    && typeof m.version_name === "string" && m.version_name.trim().length > 0
    && Number.isSafeInteger(m.version_code) && m.version_code > 0 && m.version_code <= 2100000000
    && Number.isSafeInteger(m.minimum_supported_version_code) && m.minimum_supported_version_code > 0
    && m.minimum_supported_version_code <= m.version_code
    && (m.rollback_version_code === null || (Number.isSafeInteger(m.rollback_version_code)
      && m.rollback_version_code > 0 && m.rollback_version_code < m.version_code))
    && typeof m.apk_url === "string" && validReleaseUrl(m.apk_url, m.channel)
    && typeof m.apk_sha256 === "string" && /^[a-f0-9]{64}$/.test(m.apk_sha256)
    && typeof m.published_at === "string" && !Number.isNaN(Date.parse(m.published_at))
    && (!requireSignature || (typeof m.signature === "string" && /^[A-Za-z0-9+/]{86}==$/.test(m.signature)));
}

export function canonicalReleasePayload(manifest) {
  return JSON.stringify(Object.fromEntries(payloadKeys.map((key) => [key, manifest[key]])));
}
