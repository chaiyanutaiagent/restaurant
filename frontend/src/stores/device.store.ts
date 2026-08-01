import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { DeviceContext, DevicePairResponse } from "@/types/device";

type DeviceState = {
  accessToken: string | null;
  device: DeviceContext | null;
  expiresAt: number | null;
  setSession: (session: DevicePairResponse) => void;
  updateContext: (device: DeviceContext) => void;
  clearSession: () => void;
  isAuthenticated: () => boolean;
};

export const useDeviceStore = create<DeviceState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      device: null,
      expiresAt: null,
      setSession: (session) => set({
        accessToken: session.access_token,
        device: session.device,
        expiresAt: Date.now() + session.expires_in * 1000,
      }),
      updateContext: (device) => set({ device }),
      clearSession: () => set({ accessToken: null, device: null, expiresAt: null }),
      isAuthenticated: () => {
        const state = get();
        return Boolean(
          state.accessToken
          && state.device
          && state.expiresAt
          && state.expiresAt > Date.now(),
        );
      },
    }),
    {
      name: "restaurant-device",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        device: state.device,
        expiresAt: state.expiresAt,
      }),
    },
  ),
);
