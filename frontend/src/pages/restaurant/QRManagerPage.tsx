import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, QrCode, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import QRCode from "qrcode";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { authApi } from "@/lib/api";
import { fbApi } from "@/lib/fbApi";
import { useAuthStore } from "@/stores/auth.store";

export default function QRManagerPage(): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const branchId = useAuthStore((s) => s.branchId);
  const [qsQrDataUrl, setQsQrDataUrl] = useState("");

  const settingsQuery = useQuery({
    queryKey: ["branch-settings", branchId],
    queryFn: async () => (await fbApi.settings()).data.data,
    enabled: Boolean(branchId),
  });

  const settings = settingsQuery.data;
  const hasTables = settings
    ? settings.fb_service_mode !== "quick_service"
    : false;

  // Generate QR image เมื่อมี token
  useEffect(() => {
    if (hasTables || !settings?.fb_qs_qr_token) { setQsQrDataUrl(""); return; }
    const url = `${window.location.origin}/order/${settings.fb_qs_qr_token}`;
    QRCode.toDataURL(url, { width: 300, margin: 2, color: { dark: "#1e293b" } })
      .then(setQsQrDataUrl)
      .catch(() => setQsQrDataUrl(""));
  }, [hasTables, settings?.fb_qs_qr_token]);

  const generateMutation = useMutation({
    mutationFn: async () => (await authApi.post("/restaurant/qs-qr/generate")).data.data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["branch-settings"] });
      toast({ title: "สร้าง QR สำเร็จ" });
    },
  });

  function downloadQr(dataUrl: string, name: string): void {
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = `${name}.png`;
    a.click();
  }

  function printQr(): void {
    window.print();
  }

  return (
    <div>
      <PageHeader title="QR รับออเดอร์" subtitle={hasTables ? "QR เฉพาะรอบสำหรับโต๊ะและออเดอร์รับกลับ" : "สร้างและพิมพ์ QR สำหรับลูกค้าสแกนสั่งอาหาร"} />

      <div className="grid gap-6 p-6 md:grid-cols-2">
        {/* Takeaway QR */}
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-5">
            <div className="rounded-2xl bg-orange-100 p-3">
              <QrCode className="h-6 w-6 text-orange-600" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900">{hasTables ? "QR รับกลับต่อออเดอร์" : "QR สั่งกลับบ้าน"}</h3>
              <p className="text-sm text-slate-500">{hasTables ? "เคาน์เตอร์เปิดคิวและออก QR ใหม่ให้ลูกค้าแต่ละราย" : "ลูกค้าสแกน สั่งอาหาร และรับเลขคิว"}</p>
            </div>
          </div>

          {hasTables ? (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-center">
              <QrCode className="mx-auto h-16 w-16 text-emerald-500" />
              <p className="mt-4 font-bold text-emerald-900">ร้านที่มีโต๊ะจะไม่ใช้ QR รับกลับแบบถาวร</p>
              <p className="mt-2 text-sm text-emerald-700">เปิดคิวรับกลับที่เคาน์เตอร์ ระบบจะออกเลขคิวและ QR ที่ใช้ได้เฉพาะออเดอร์นั้น</p>
              <Button className="mt-5 bg-emerald-600 hover:bg-emerald-700" asChild>
                <Link to="/restaurant/tables">ไปที่แผนที่โต๊ะเพื่อออก QR</Link>
              </Button>
            </div>
          ) : qsQrDataUrl ? (
            <>
              <div className="flex justify-center">
                <div className="rounded-3xl border-4 border-orange-200 bg-white p-4 shadow-md print:border-0">
                  <img src={qsQrDataUrl} alt="QR สั่งกลับบ้าน" className="h-64 w-64" />
                  <p className="mt-3 text-center text-sm font-semibold text-slate-700">สแกนเพื่อสั่งอาหาร</p>
                  <p className="text-center text-xs text-slate-400">{settingsQuery.data?.fb_queue_prefix ? `ระบบคิว: ${settingsQuery.data.fb_queue_prefix}XXX` : "ระบบคิวอัตโนมัติ"}</p>
                </div>
              </div>

              <div className="mt-4 flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => downloadQr(qsQrDataUrl, "shop-qr")}>
                  <Download className="mr-2 h-4 w-4" /> ดาวน์โหลด
                </Button>
                <Button variant="outline" className="flex-1" onClick={printQr}>
                  พิมพ์
                </Button>
                <Button
                  variant="outline"
                  className="text-red-500 hover:bg-red-50"
                  onClick={() => window.confirm("สร้าง QR ใหม่? QR เดิมจะใช้ไม่ได้") && generateMutation.mutate()}
                >
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>

              <div className="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                <p className="font-medium">URL:</p>
                <p className="mt-1 break-all text-xs font-mono text-blue-600">
                  {window.location.origin}/order/{settingsQuery.data?.fb_qs_qr_token}
                </p>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <QrCode className="h-16 w-16 text-slate-200 mb-4" />
              <p className="text-slate-500 mb-4">ยังไม่มี QR สำหรับสั่งกลับบ้าน</p>
              <Button
                className="bg-orange-500 hover:bg-orange-600"
                onClick={() => generateMutation.mutate()}
                disabled={generateMutation.isPending}
              >
                {generateMutation.isPending ? "กำลังสร้าง..." : "สร้าง QR"}
              </Button>
            </div>
          )}
        </div>

        {/* Info panel */}
        <div className="space-y-4">
          <div className="rounded-2xl border border-blue-200 bg-blue-50 p-5">
            <h4 className="mb-3 font-semibold text-blue-800">{hasTables ? "วิธีออก QR รับกลับที่เคาน์เตอร์" : "วิธีใช้งาน QR สั่งกลับบ้าน"}</h4>
            {hasTables ? (
              <ol className="space-y-2 text-sm text-blue-700">
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">1.</span>เข้าแผนที่โต๊ะ แล้วกด “ออก QR รับกลับ”</li>
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">2.</span>กรอกชื่อลูกค้าหรือเบอร์โทรถ้ามี แล้วเปิดคิว</li>
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">3.</span>พิมพ์ QR ให้ลูกค้าสแกนเลือกเมนู</li>
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">4.</span>รายการจะเข้า Kitchen Display พร้อมเลขคิวรับกลับ</li>
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">5.</span>เมื่อรับอาหารแล้ว ปิดคิวเพื่อให้ QR หมดอายุ</li>
              </ol>
            ) : (
              <ol className="space-y-2 text-sm text-blue-700">
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">1.</span>พิมพ์ QR แล้วติดที่เคาน์เตอร์</li>
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">2.</span>ลูกค้าสแกน QR ด้วยกล้องโทรศัพท์</li>
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">3.</span>เลือกเมนู ใส่ตะกร้า กด “สั่งอาหาร”</li>
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">4.</span>ระบบออกเลขคิวให้อัตโนมัติ</li>
                <li className="flex gap-2"><span className="flex-shrink-0 font-bold">5.</span>เมื่อครัวทำเสร็จ ลูกค้าจะเห็นสถานะพร้อมรับ</li>
              </ol>
            )}
          </div>

          {hasTables ? (
            <>
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
                <h4 className="font-semibold text-amber-800 mb-2">QR ทั้งสองแบบเป็น QR ต่อรอบ</h4>
                <div className="space-y-1 text-sm text-amber-700">
                  <p>• <strong>รับกลับ:</strong> เคาน์เตอร์เปิดคิวและพิมพ์ QR เฉพาะลูกค้ารายนั้น</p>
                  <p>• <strong>นั่งทาน:</strong> เปิดโต๊ะและพิมพ์ QR สำหรับรอบของโต๊ะนั้น</p>
                  <p>• เมื่อปิดโต๊ะหรือปิดคิว QR จะหมดอายุทันที</p>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <h4 className="font-semibold text-slate-700 mb-2">QR ต่อรอบเปิดโต๊ะ</h4>
                <p className="text-sm text-slate-500">เปิดโต๊ะเพื่อสร้างและพิมพ์ QR ที่ใช้ได้เฉพาะรอบนั้น</p>
                <Button variant="outline" className="mt-2 w-full" asChild>
                  <Link to="/restaurant/tables">แผนที่โต๊ะ →</Link>
                </Button>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
