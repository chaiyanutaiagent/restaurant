import { Capacitor, registerPlugin } from "@capacitor/core";

export type TakeawayStoreReleaseManifest = {
  surface: "takeaway_store";
  channel: "uat" | "production";
  package_id: string;
  version_name: string;
  version_code: number;
  minimum_supported_version_code: number;
  rollback_version_code: number | null;
  apk_url: string;
  apk_sha256: string;
  published_at: string;
  signature: string;
};

type InstalledApp = {
  packageId: string;
  versionName: string;
  versionCode: number;
  installPermission: boolean;
};

type TakeawayUpdaterNative = {
  getStatus(): Promise<InstalledApp>;
  installUpdate(options: { apkUrl: string; apkSha256: string; versionCode: number }): Promise<void>;
};

export type TakeawayStoreRelease = {
  manifest: TakeawayStoreReleaseManifest;
  installed: InstalledApp;
  verified: boolean;
  updateAvailable: boolean;
  updateRequired: boolean;
};

const nativeUpdater = registerPlugin<TakeawayUpdaterNative>("TakeawayUpdater");

function canonicalPayload(manifest: TakeawayStoreReleaseManifest): string {
  return JSON.stringify({
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
  });
}

function bytesFromBase64(value: string): ArrayBuffer {
  const binary = window.atob(value);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0)).buffer as ArrayBuffer;
}

function spkiFromPem(pem: string): ArrayBuffer {
  return bytesFromBase64(pem.replace(/-----[^-]+-----/g, "").replace(/\s+/g, ""));
}

function configuredValue(name: "url" | "key" | "package" | "channel"): string {
  const values = {
    url: import.meta.env.VITE_TAKEAWAY_STORE_RELEASE_MANIFEST_URL as string | undefined,
    key: import.meta.env.VITE_TAKEAWAY_STORE_RELEASE_PUBLIC_KEY as string | undefined,
    package: import.meta.env.VITE_TAKEAWAY_STORE_PACKAGE_ID as string | undefined,
    channel: import.meta.env.VITE_TAKEAWAY_STORE_RELEASE_CHANNEL as string | undefined,
  };
  const value = values[name]?.trim();
  if (!value) throw new Error("ยังไม่ได้ตั้งค่าช่องอัปเดต Store");
  return value;
}

function validManifest(value: unknown): value is TakeawayStoreReleaseManifest {
  if (!value || typeof value !== "object") return false;
  const manifest = value as Record<string, unknown>;
  return manifest.surface === "takeaway_store"
    && (manifest.channel === "uat" || manifest.channel === "production")
    && typeof manifest.package_id === "string"
    && typeof manifest.version_name === "string"
    && Number.isSafeInteger(manifest.version_code)
    && Number.isSafeInteger(manifest.minimum_supported_version_code)
    && Number(manifest.version_code) > 0
    && Number(manifest.minimum_supported_version_code) > 0
    && Number(manifest.minimum_supported_version_code) <= Number(manifest.version_code)
    && (manifest.rollback_version_code === null || Number.isSafeInteger(manifest.rollback_version_code))
    && typeof manifest.apk_url === "string"
    && /^https:\/\//.test(manifest.apk_url)
    && typeof manifest.apk_sha256 === "string"
    && /^[a-f0-9]{64}$/i.test(manifest.apk_sha256)
    && typeof manifest.published_at === "string"
    && !Number.isNaN(Date.parse(manifest.published_at))
    && typeof manifest.signature === "string";
}

export async function verifyTakeawayStoreReleaseManifest(
  manifest: TakeawayStoreReleaseManifest,
  publicKeyPem: string,
): Promise<boolean> {
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

export async function loadTakeawayRelease(): Promise<TakeawayStoreRelease> {
  if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== "android") {
    throw new Error("ช่องอัปเดตนี้ใช้สำหรับแอป Android เท่านั้น");
  }
  const url = configuredValue("url");
  const publicKey = configuredValue("key").replace(/\\n/g, "\n");
  const expectedPackage = configuredValue("package");
  const expectedChannel = configuredValue("channel");
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("โหลดข้อมูลอัปเดตไม่สำเร็จ");
  const candidate: unknown = await response.json();
  if (!validManifest(candidate)) throw new Error("รูปแบบข้อมูลอัปเดตไม่ถูกต้อง");
  if (candidate.package_id !== expectedPackage || candidate.channel !== expectedChannel) {
    throw new Error("ข้อมูลอัปเดตไม่ตรงกับแอปหรือสภาพแวดล้อมนี้");
  }
  const verified = await verifyTakeawayStoreReleaseManifest(candidate, publicKey);
  if (!verified) throw new Error("ลายเซ็นข้อมูลอัปเดตไม่ถูกต้อง");
  const installed = await nativeUpdater.getStatus();
  if (installed.packageId !== expectedPackage) throw new Error("Package ของแอปไม่ตรงกับช่องอัปเดต");
  return {
    manifest: candidate,
    installed,
    verified,
    updateAvailable: candidate.version_code > installed.versionCode,
    updateRequired: candidate.minimum_supported_version_code > installed.versionCode,
  };
}

export async function installTakeawayRelease(release: TakeawayStoreRelease): Promise<void> {
  if (!release.verified || !release.updateAvailable) throw new Error("ไม่มีอัปเดตที่ผ่านการตรวจสอบ");
  await nativeUpdater.installUpdate({
    apkUrl: release.manifest.apk_url,
    apkSha256: release.manifest.apk_sha256,
    versionCode: release.manifest.version_code,
  });
}
