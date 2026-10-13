import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export default function ProductBarcodeScanner({ open, onClose, onScan }: {
  open: boolean; onClose: () => void; onScan: (code: string) => void;
}): JSX.Element {
  const video = useRef<HTMLVideoElement>(null);
  const callback = useRef(onScan);
  callback.current = onScan;
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    let handled = false;
    let controls: { stop: () => void } | undefined;
    setError("");
    void (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("เปิดผ่าน HTTPS และใช้เบราว์เซอร์ที่รองรับกล้อง");
        const { BrowserMultiFormatReader } = await import("@zxing/browser");
        if (cancelled || !video.current) return;
        const reader = new BrowserMultiFormatReader();
        controls = await reader.decodeFromConstraints({audio:false,video:{facingMode:{ideal:"environment"}}}, video.current,
          (result, _error, scanner) => {
            if (!cancelled && !handled && result?.getText().trim()) {
              handled = true;
              scanner.stop();
              callback.current(result.getText().trim());
            }
          });
        if (cancelled) controls.stop();
      } catch (error) {
        if (!cancelled) setError(error instanceof Error && error.message.includes("HTTPS") ? error.message : "เปิดกล้องไม่ได้ กรุณาอนุญาตกล้อง หรือกรอก/ยิงบาร์โค้ดแทน");
      }
    })();
    return () => { cancelled = true; controls?.stop(); };
  }, [open]);
  return <Dialog open={open} onOpenChange={value => {if (!value) onClose();}}><DialogContent>
    <DialogHeader><DialogTitle>สแกนบาร์โค้ดสินค้า</DialogTitle><DialogDescription>วางบาร์โค้ดให้ชัด ระบบจะตรวจสินค้าเดิมก่อนสร้างรายการใหม่</DialogDescription></DialogHeader>
    <video ref={video} autoPlay muted playsInline className="aspect-video w-full rounded-xl bg-slate-950" />
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
  </DialogContent></Dialog>;
}
