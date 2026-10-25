import { create } from "zustand";
import { parseDevicePairingLink, type PairingLink } from "@/lib/devicePairingLink";
import { nativeProduct } from "./config";

// Pending PINs stay in memory only; they never replace an existing device session.
export const usePendingPairing = create<{
  pending: PairingLink | null; error: string; receive: (raw: string) => void; clear: () => void;
}>((set) => ({
  pending: null, error: "",
  receive(raw) {
    try {
      if (!nativeProduct) throw new Error("ไม่พบประเภทแอป");
      set({ pending: parseDevicePairingLink(raw, nativeProduct), error: "" });
    } catch (error) {
      set({ pending: null, error: error instanceof Error ? error.message : "อ่าน QR ไม่ได้" });
    }
  },
  clear: () => set({ pending: null, error: "" }),
}));
