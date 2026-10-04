export type TakeawayReleaseManifest = {
  channel: "uat" | "production";
  package_id: "com.foodchainservice.takeaway";
  version_name: string;
  version_code: number;
  minimum_supported_version_code: number;
  rollback_version_code: number | null;
  apk_url: string;
  apk_sha256: string;
  published_at: string;
  signature: string;
};

function canonicalPayload(manifest: TakeawayReleaseManifest): string {
  return JSON.stringify({
    apk_sha256: manifest.apk_sha256,
    apk_url: manifest.apk_url,
    channel: manifest.channel,
    minimum_supported_version_code: manifest.minimum_supported_version_code,
    package_id: manifest.package_id,
    published_at: manifest.published_at,
    rollback_version_code: manifest.rollback_version_code,
    version_code: manifest.version_code,
    version_name: manifest.version_name,
  });
}

function bytesFromBase64(value: string): ArrayBuffer {
  const binary = window.atob(value);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0)).buffer as ArrayBuffer;
}

function spkiFromPem(pem: string): ArrayBuffer {
  return bytesFromBase64(pem.replace(/-----[^-]+-----/g, "").replace(/\s+/g, ""));
}

export async function verifyTakeawayReleaseManifest(
  manifest: TakeawayReleaseManifest,
  publicKeyPem: string,
): Promise<boolean> {
  if (manifest.package_id !== "com.foodchainservice.takeaway") return false;
  if (!/^[a-f0-9]{64}$/i.test(manifest.apk_sha256)) return false;
  try {
    const key = await window.crypto.subtle.importKey(
      "spki",
      spkiFromPem(publicKeyPem),
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    return window.crypto.subtle.verify(
      { name: "Ed25519" },
      key,
      bytesFromBase64(manifest.signature),
      new TextEncoder().encode(canonicalPayload(manifest)).buffer as ArrayBuffer,
    );
  } catch {
    return false;
  }
}

export async function loadTakeawayRelease(): Promise<{
  manifest: TakeawayReleaseManifest;
  verified: boolean;
}> {
  const url = import.meta.env.VITE_TAKEAWAY_RELEASE_MANIFEST_URL as string | undefined;
  const publicKey = import.meta.env.VITE_TAKEAWAY_RELEASE_PUBLIC_KEY as string | undefined;
  if (!url || !publicKey) throw new Error("ยังไม่ได้ตั้งค่า signed release channel");
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("โหลด release manifest ไม่สำเร็จ");
  const manifest = await response.json() as TakeawayReleaseManifest;
  return { manifest, verified: await verifyTakeawayReleaseManifest(manifest, publicKey.replace(/\\n/g, "\n")) };
}
