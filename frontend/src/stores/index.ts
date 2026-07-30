import { create } from "zustand";

type AppState = {
  accessToken: string | null;
  setAccessToken: (token: string | null) => void;
};

export const useAppStore = create<AppState>((set) => ({
  accessToken: null,
  setAccessToken: (token) => set({ accessToken: token })
}));
