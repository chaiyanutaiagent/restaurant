import PairingReader from "@/components/devices/PairingReader";
import { usePendingPairing } from "./pairing";

export default function PairingScanner({ disabled = false }: { disabled?: boolean }) {
  const state = usePendingPairing();
  return <PairingReader {...state} disabled={disabled} />;
}
