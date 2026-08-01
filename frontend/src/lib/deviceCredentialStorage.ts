import { SecureStorage } from "@aparajita/capacitor-secure-storage";
import type { DeviceContext } from "@/types/device";

const DEVICE_SESSION_KEY = "restaurant-device-session-v2";
const LEGACY_DEVICE_SESSION_KEY = "restaurant-device";
const STORAGE_PROBE_KEY = "restaurant-device-storage-probe";

export type StoredDeviceSession = {
  accessToken: string | null;
  refreshToken: string | null;
  device: DeviceContext | null;
  expiresAt: number | null;
};

function parseSession(raw: string | null): StoredDeviceSession | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredDeviceSession>;
    if (!parsed.device || typeof parsed.device.device_id !== "string") return null;
    return {
      accessToken: typeof parsed.accessToken === "string" ? parsed.accessToken : null,
      refreshToken: typeof parsed.refreshToken === "string" ? parsed.refreshToken : null,
      device: parsed.device,
      expiresAt: typeof parsed.expiresAt === "number" ? parsed.expiresAt : null,
    };
  } catch {
    return null;
  }
}

function readLegacySession(): StoredDeviceSession | null {
  try {
    const raw = window.localStorage.getItem(LEGACY_DEVICE_SESSION_KEY);
    if (!raw) return null;
    const legacy = JSON.parse(raw) as { state?: Partial<StoredDeviceSession> };
    return parseSession(JSON.stringify({
      accessToken: legacy.state?.accessToken ?? null,
      refreshToken: null,
      device: legacy.state?.device ?? null,
      expiresAt: legacy.state?.expiresAt ?? null,
    }));
  } catch {
    return null;
  }
}

export async function loadStoredDeviceSession(): Promise<StoredDeviceSession | null> {
  const current = parseSession(await SecureStorage.getItem(DEVICE_SESSION_KEY));
  if (current) return current;

  const legacy = readLegacySession();
  if (legacy) {
    await saveStoredDeviceSession(legacy);
    window.localStorage.removeItem(LEGACY_DEVICE_SESSION_KEY);
  }
  return legacy;
}

export async function assertDeviceCredentialStorageAvailable(): Promise<void> {
  try {
    const probe = `ready-${Date.now()}`;
    await SecureStorage.setItem(STORAGE_PROBE_KEY, probe);
    const restored = await SecureStorage.getItem(STORAGE_PROBE_KEY);
    await SecureStorage.removeItem(STORAGE_PROBE_KEY);
    if (restored === probe) return;
  } catch {
    // Normalize native and browser storage failures into an operator-safe message.
  }
  try {
    await SecureStorage.removeItem(STORAGE_PROBE_KEY);
  } finally {
    throw new Error("พื้นที่เก็บรหัสเครื่องไม่พร้อม กรุณาปิดและเปิดแอปแล้วลองใหม่");
  }
}

export async function saveStoredDeviceSession(session: StoredDeviceSession): Promise<void> {
  await SecureStorage.setItem(DEVICE_SESSION_KEY, JSON.stringify(session));
}

export async function clearStoredDeviceSession(): Promise<void> {
  await SecureStorage.removeItem(DEVICE_SESSION_KEY);
  window.localStorage.removeItem(LEGACY_DEVICE_SESSION_KEY);
}
