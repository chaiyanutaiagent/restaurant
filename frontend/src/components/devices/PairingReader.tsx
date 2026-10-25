import { useEffect, useRef, useState } from "react";
import { BrowserQRCodeReader, type IScannerControls } from "@zxing/browser";
import type { PairingLink } from "@/lib/devicePairingLink";

export default function PairingReader({ receive, pending, error, disabled = false }: {
  receive: (raw: string) => void; pending: PairingLink | null; error: string; disabled?: boolean;
}) {
  const [scanning, setScanning] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [link, setLink] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (!scanning || !video.current || disabled) return;
    let stopped = false;
    let controls: IScannerControls | undefined;
    void new BrowserQRCodeReader().decodeFromConstraints({ video: { facingMode: { ideal: "environment" } } }, video.current, result => {
      if (result && !stopped) { receive(result.getText()); setScanning(false); }
    }).then(value => { controls = value; if (stopped) value.stop(); }).catch(() => {
      if (!stopped) { setCameraError("เปิดกล้องไม่ได้ ให้เลือกภาพ QR หรือวางลิงก์แทน"); setScanning(false); }
    });
    return () => { stopped = true; controls?.stop(); };
  }, [scanning, receive, disabled]);
  return <fieldset disabled={disabled} className="space-y-3 rounded-xl border bg-blue-50 p-4">
    <h2 className="font-bold">QR จับคู่ Counter จากหลังบ้าน</h2>
    <button type="button" className="min-h-12 rounded border bg-white p-3" onClick={() => { setCameraError(""); setScanning(!scanning); }}>{scanning ? "ปิดกล้อง" : "สแกน QR จับคู่เครื่อง"}</button>
    {scanning && <video ref={video} autoPlay playsInline muted className="w-full rounded" />}
    <label className="block">หรือเลือกภาพ QR<input type="file" accept="image/*" className="block w-full" onChange={async event => {
      const file = event.target.files?.[0]; event.target.value = "";
      if (!file) return;
      setScanning(false); setCameraError("");
      if (file.size > 10 * 1024 * 1024) { setCameraError("ภาพต้องไม่เกิน 10 MB"); return; }
      const url = URL.createObjectURL(file);
      try { receive((await new BrowserQRCodeReader().decodeFromImageUrl(url)).getText()); }
      catch { setCameraError("อ่านภาพ QR ไม่ได้ กรุณาใช้ภาพต้นฉบับหรือวางลิงก์"); }
      finally { URL.revokeObjectURL(url); }
    }}/></label>
    <label className="block">วางลิงก์จับคู่<input value={link} onChange={event => setLink(event.target.value)} autoComplete="off" className="block min-h-12 w-full rounded border p-3" /></label>
    <button type="button" disabled={!link.trim()} className="min-h-12 rounded border bg-white p-3" onClick={() => { receive(link); setLink(""); }}>อ่านลิงก์จับคู่</button>
    {pending && <p role="status">อ่านรหัสเครื่อง {pending.deviceCode} แล้ว ต้องเข้าสู่ระบบบริษัท/สาขาที่ตรงกันและกดยืนยันจับคู่</p>}
    {(cameraError || error) && <p role="alert" className="text-red-700">{cameraError || error}</p>}
  </fieldset>;
}
