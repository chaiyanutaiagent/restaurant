import { create } from "zustand";
import {
  clearStoredDeviceSession,
  loadStoredDeviceSession,
  saveStoredDeviceSession,
  type StoredDeviceSession,
} from "@/lib/deviceCredentialStorage";
import type { DeviceContext, DevicePairResponse } from "@/types/device";

type DeviceState = StoredDeviceSession & {
  hydrated: boolean;
  hydrate: () => Promise<void>;
  setSession: (session: DevicePairResponse) => Promise<void>;
  updateContext: (device: DeviceContext) => Promise<void>;
  clearSession: () => Promise<void>;
  isAuthenticated: () => boolean;
};

let hydrationPromise: Promise<void> | null = null;

export const useDeviceStore = create<DeviceState>()((set, get) => ({
  accessToken: null,
  refreshToken: null,
  device: null,
  expiresAt: null,
  hydrated: false,
  hydrate: async () => {
    if (get().hydrated) return;
    if (!hydrationPromise) {
      hydrationPromise = (async () => {
        let stored: StoredDeviceSession | null = null;
        try {
          stored = await loadStoredDeviceSession();
        } catch {
          await clearStoredDeviceSession().catch(() => undefined);
        }
        set({
          accessToken: stored?.accessToken ?? null,
          refreshToken: stored?.refreshToken ?? null,
          device: stored?.device ?? null,
          expiresAt: stored?.expiresAt ?? null,
          hydrated: true,
        });
      })().finally(() => {
        hydrationPromise = null;
      });
    }
    await hydrationPromise;
  },
  setSession: async (session) => {
    const stored: StoredDeviceSession = {
      accessToken: session.access_token,
      refreshToken: session.refresh_token,
      device: session.device,
      expiresAt: Date.now() + session.expires_in * 1000,
    };
    set({ ...stored, hydrated: true });
    await saveStoredDeviceSession(stored);
  },
  updateContext: async (device) => {
    set({ device });
    const state = get();
    await saveStoredDeviceSession({
      accessToken: state.accessToken,
      refreshToken: state.refreshToken,
      device,
      expiresAt: state.expiresAt,
    });
  },
  clearSession: async () => {
    set({
      accessToken: null,
      refreshToken: null,
      device: null,
      expiresAt: null,
      hydrated: true,
    });
    await clearStoredDeviceSession();
  },
  isAuthenticated: () => {
    const state = get();
    return Boolean(
      state.accessToken
      && state.device
      && state.expiresAt
      && state.expiresAt > Date.now(),
    );
  },
}));
