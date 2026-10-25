import { Download, Loader2, QrCode, Share2 } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { DeviceProvisioning } from "@/types/device";
import { useAuthStore } from "@/stores/auth.store";
import { androidPairingIntent } from "@/lib/devicePairingLink";
import { pairingApps, pairingProduct } from "@/lib/pairingAppDownloads";

export default function DeviceProvisioningPanel({ provisioning, retail = false }: { provisioning: DeviceProvisioning; retail?: boolean }): JSX.Element {
  const businessSlug = useAuthStore(state => state.businessSlug);
  const [qrUrl, setQrUrl] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const expires = new Date(provisioning.pairing_expires_at);
  const expired = !Number.isFinite(expires.getTime()) || now >= expires.getTime();
  const payload = new URL(provisioning.pairing_qr_payload);
  if (retail && provisioning.device.device_type === "counter") {
    payload.searchParams.set("target_app", "retail");
    payload.searchParams.set("branch_id", provisioning.device.branch_id);
    payload.searchParams.set("expires_at", provisioning.pairing_expires_at);
    if (businessSlug) payload.searchParams.set("business_code", businessSlug);
  }
  const product = pairingProduct(payload.searchParams.get("target_app"));
  const pairingUrl = product
    ? `https://uat-app.foodchainservice.com/device/pair/${product}?${payload.searchParams.toString()}`
    : `${window.location.origin}/device/pair?${payload.searchParams.toString()}`;
  const filename = `foodchainservice-pair-${provisioning.device.device_code.replace(/[^a-zA-Z0-9_-]/g, "")}.png`;

  useEffect(() => {
    let active = true;
    void QRCode.toDataURL(pairingUrl, { width: 640, margin: 4, errorCorrectionLevel: "M" })
      .then(url => { if (active) setQrUrl(url); })
      .catch(() => { if (active) setMessage("สร้างรูป QR ไม่สำเร็จ กรุณาลองเปิดหน้านี้ใหม่"); });
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [pairingUrl]);

  function downloadQr() {
    if (!qrUrl || Date.now() >= expires.getTime()) return;
    const link = document.createElement("a");
    link.href = qrUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setMessage("ดาวน์โหลดรูป QR แล้ว ส่งรูปให้ผู้ใช้เครื่องนั้นทาง LINE หรือช่องทางที่ต้องการได้");
  }

  async function shareQr() {
    if (!qrUrl || Date.now() >= expires.getTime()) return;
    setBusy(true);
    setMessage("");
    try {
      // Prepare the file synchronously so the browser's share gesture is retained.
      const bytes = Uint8Array.from(atob(qrUrl.split(",")[1]), char => char.charCodeAt(0));
      const file = new File([bytes], filename, { type: "image/png" });
      if (!navigator.share || !navigator.canShare?.({ files: [file] })) {
        downloadQr();
        return;
      }
      await navigator.share({ files: [file], title: `จับคู่ ${provisioning.device.name}`,
        text: `QR จับคู่ ${provisioning.device.name} (${provisioning.device.device_code}) ใช้ครั้งเดียว หมดอายุ ${expires.toLocaleString("th-TH")} ส่งเฉพาะผู้ใช้เครื่องนี้` });
      setMessage("ส่งรูปให้หน้าต่างแชร์แล้ว");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      setMessage("แชร์รูปไม่ได้ กรุณากดดาวน์โหลด QR แล้วแนบรูปส่งเอง");
    } finally {
      setBusy(false);
    }
  }

  return <Card className="border-emerald-300 bg-emerald-50">
    <CardHeader>
      <CardTitle className="flex items-center gap-2 text-emerald-950"><QrCode className="h-5 w-5" />ข้อมูลจับคู่ครั้งเดียว</CardTitle>
      <CardDescription>{provisioning.device.name} · หมดอายุ {expires.toLocaleString("th-TH")} · ใช้ได้ครั้งเดียว</CardDescription>
    </CardHeader>
    <CardContent className="grid items-center gap-6 md:grid-cols-[1fr_auto]">
      <div className="space-y-4">
        <div><p className="text-xs font-semibold text-emerald-800">Device Code</p><p className="mt-1 font-mono text-2xl font-black text-emerald-950">{provisioning.device.device_code}</p></div>
        {expired ? <p role="alert" className="font-semibold text-red-700">QR / PIN หมดอายุแล้ว กด PIN ใหม่ในรายการเครื่องเดิม</p>
          : <div><p className="text-xs font-semibold text-emerald-800">Pairing PIN</p><p className="mt-1 font-mono text-5xl font-black tracking-[0.25em] text-emerald-950">{provisioning.pairing_pin}</p></div>}
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={!qrUrl || expired || busy} onClick={() => void shareQr()}><Share2 className="h-4 w-4" />แชร์รูป QR</Button>
          <Button type="button" variant="outline" disabled={!qrUrl || expired || busy} onClick={downloadQr}><Download className="h-4 w-4" />ดาวน์โหลด QR</Button>
          {!expired && <Button asChild type="button" variant="outline"><a href={pairingUrl}>เปิดหน้าจับคู่เครื่องนี้</a></Button>}
          {!expired && product && <Button asChild type="button" variant="outline"><a href={androidPairingIntent(pairingUrl, product)}>เปิดแอป {pairingApps[product].name} บน Android</a></Button>}
          <Button type="button" variant="outline" disabled={expired} onClick={() => {
            void navigator.clipboard.writeText(pairingUrl).then(() => setMessage("คัดลอกลิงก์จับคู่แล้ว"))
              .catch(() => setMessage("คัดลอกไม่ได้ กรุณาดาวน์โหลดรูป QR แทน"));
          }}>คัดลอกลิงก์จับคู่</Button>
        </div>
        <p className="text-sm text-emerald-950">ส่งเฉพาะผู้ใช้เครื่องนี้เท่านั้น รูปและลิงก์มีข้อมูลสำหรับจับคู่ หากแชร์รูปไม่ได้ระบบจะดาวน์โหลดให้</p>
        <p className="text-sm text-emerald-950">ลิงก์ใหม่มีอายุ 24 ชั่วโมงและใช้จับคู่ได้ครั้งเดียว Android เปิดแอปที่ตรงระบบหรือหน้าดาวน์โหลด ส่วน Mac/PC ใช้ผ่านเว็บ หากมีแอปแล้วสามารถเลือกภาพ QR ในแอปได้ ไม่ต้องกรอก Business Code ซ้ำ</p>
        {message && <p role="status" className="text-sm font-medium text-emerald-950">{message}</p>}
      </div>
      {!expired && (qrUrl ? <img src={qrUrl} alt="QR สำหรับจับคู่อุปกรณ์" className="mx-auto w-56 rounded-2xl border-8 border-white" /> : <Loader2 className="h-8 w-8 animate-spin" />)}
    </CardContent>
  </Card>;
}
